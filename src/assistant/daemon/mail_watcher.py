"""Watches inboxes while something wants their new mail: an account's alerts (Settings → email), or
jobs that run on new mail, which use the default account. Supervised inside the daemon like a
channel adapter.

One IMAP connection per watched account waits in IDLE, so the server tells it about new mail. New
messages are announced on the account's alerts channel and, for the default account, handed to the
mail jobs. The last UID seen is kept in the Store per account, before anything is delivered, so a
restart neither repeats messages nor floods the user with old ones. Connections are reopened when
the accounts change, and kept closed while nothing wants new mail.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from assistant.core.agent import AssistantService
from assistant.core.config import settings
from assistant.core.conversation import sent
from assistant.core.hidden_text import strip_hidden
from assistant.core.integrations.email import accounts, imap
from assistant.core.integrations.email.accounts import EmailConfig, EmailError
from assistant.core.integrations.email.imap import Mailbox, MailSummary
from assistant.core.jobs import store as jobs
from assistant.core.outbox import DeliveryError
from assistant.daemon.scheduler import Scheduler

logger = logging.getLogger(__name__)

_NAMESPACE = ("mail_watch",)
# Servers end IDLE after 30 minutes; it's renewed before that.
_IDLE_SECONDS = 25 * 60
_FIRST_RETRY_SECONDS = 30
_MAX_RETRY_SECONDS = 600
# Store writes that may change what to watch.
# Accounts, mail jobs, and plugins (an email plugin turned on or off brings its accounts or takes them).
_CHANGES = {"integrations", "jobs", "mcp"}


class MailWatcher:
    name = "mail"

    def __init__(self, service: AssistantService, scheduler: Scheduler) -> None:
        self._service = service
        self._scheduler = scheduler

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            configs = await self._wanted()
            watching = [asyncio.create_task(self._watch(c)) for c in configs]
            try:
                await _first(stop.wait(), self._until_changed(configs))
            finally:
                for task in watching:
                    task.cancel()
                for task in watching:
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

    async def _wanted(self) -> list[EmailConfig]:
        """The accounts to watch, with their passwords: those that can read mail and have alerts on,
        and the default one while mail jobs exist."""
        mail_jobs = bool(await self._mail_jobs())
        wanted = []
        for listed in await accounts.list_accounts(self._service.store):
            if listed.can_read and (listed.new_mail_alerts or (listed.default and mail_jobs)):
                try:
                    wanted.append(await accounts.load(self._service.store, self._service.secrets, listed.account_id))
                except EmailError as e:
                    logger.warning("Not watching %s for new mail: %s", listed.label, e)
        return wanted

    async def _until_changed(self, current: list[EmailConfig]) -> None:
        """Returns when the accounts change what or how to watch."""
        async for event in self._service.bus.subscribe(self._service.bus.last_id):
            if event.kind in _CHANGES and _connections(await self._wanted()) != _connections(current):
                return

    async def _watch(self, config: EmailConfig) -> None:
        delay = _FIRST_RETRY_SECONDS
        while True:
            try:
                await self._session(config)
            except EmailError as e:
                logger.warning("Watching for new mail failed, retrying in %ss: %s", delay, e)
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RETRY_SECONDS)

    async def _session(self, config: EmailConfig) -> None:
        async with imap.open_mailbox(config) as mailbox:
            logger.info("Watching %s (%s) for new mail.", config.label, config.imap_host)
            last = await self._last_seen(config, mailbox)
            while True:
                last = await self._check(config, mailbox, last)
                await mailbox.wait_for_new(_IDLE_SECONDS)

    async def _check(self, config: EmailConfig, mailbox: Mailbox, last: int) -> int:
        new = await mailbox.uids_after(last)
        if not new:
            return last
        mails = await mailbox.summaries(new)
        await self._save_last_seen(config, mailbox, max(new))
        await self._deliver(config.account_id, mails)
        return max(new)

    async def _deliver(self, account_id: str, mails: list[MailSummary]) -> None:
        """Reads the account again, so a changed alerts channel or default applies right away."""
        config = await accounts.get(self._service.store, account_id)
        if config is None:
            return
        if config.new_mail_alerts:
            await self._alert(config.new_mail_alerts, config.label, mails)
        if config.default:
            for job in await self._mail_jobs():
                await self._scheduler.run_for_mail(job, mails)

    async def _alert(self, channel: str, label: str, mails: list[MailSummary]) -> None:
        text = _alert_text(mails, label)
        try:
            await self._service.outbox.send(channel, text)
        except DeliveryError as e:
            logger.warning("Couldn't announce new mail on %s: %s", channel, e)
            return
        await sent.record(self._service.store, settings.owner_id, channel, text, datetime.now(UTC))

    async def _mail_jobs(self) -> list[jobs.Job]:
        return [j for j in await jobs.all_jobs(self._service.store) if j.enabled and j.on_new_mail]

    async def _last_seen(self, config: EmailConfig, mailbox: Mailbox) -> int:
        """The last UID handled. On the first run, or after the server renumbered the inbox, the
        newest message: only mail from now on counts as new."""
        item = await self._service.store.aget(_NAMESPACE, _account(config))
        if item is not None and item.value["uid_validity"] == mailbox.uid_validity:
            return int(item.value["uid"])
        uid = await mailbox.last_uid()
        await self._save_last_seen(config, mailbox, uid)
        return uid

    async def _save_last_seen(self, config: EmailConfig, mailbox: Mailbox, uid: int) -> None:
        value = {"uid": uid, "uid_validity": mailbox.uid_validity}
        await self._service.store.aput(_NAMESPACE, _account(config), value)


def _alert_text(mails: list[MailSummary], label: str) -> str:
    lines = [f"• {m.sender}: {m.subject or '(no subject)'}" for m in mails]
    heading = "📧 New email" if len(mails) == 1 else f"📧 {len(mails)} new emails"
    return strip_hidden("\n".join([f"{heading} in {label}", *lines]))


def _account(config: EmailConfig) -> str:
    return f"{config.username}@{config.imap_host}"


def _connections(configs: list[EmailConfig]) -> set[tuple]:
    """What a change to needs new connections."""
    return {(c.account_id, c.imap_host, c.imap_port, c.username, c.password) for c in configs}


async def _first(*waits) -> None:
    tasks = [asyncio.ensure_future(w) for w in waits]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
