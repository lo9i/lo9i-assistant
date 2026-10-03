"""The mail watcher: watches only while alerts or mail jobs want new mail, starts from the newest
message, announces new mail and hands it to mail jobs. The mailbox is a fake."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from assistant.core.integrations.email import imap, smtp
from assistant.core.integrations.email.imap import MailSummary
from assistant.core.jobs import store
from assistant.core.jobs.store import Job
from assistant.daemon import mail_watcher
from assistant.daemon.mail_watcher import MailWatcher
from tests.conftest import collect


class _Mailbox:
    def __init__(self) -> None:
        self.uid_validity = "1"
        self.mails = {1: MailSummary(1, "old@x.com", "Old", "", False)}
        self.arrived = asyncio.Event()
        self.opened = 0
        # The email account the fixture connected.
        self.account = ""

    def receive(self, uid: int, sender: str, subject: str) -> None:
        self.mails[uid] = MailSummary(uid, sender, subject, "", True)
        self.arrived.set()

    async def last_uid(self) -> int:
        return max(self.mails)

    async def uids_after(self, uid: int) -> list[int]:
        return sorted(u for u in self.mails if u > uid)

    async def summaries(self, uids):
        return [self.mails[u] for u in uids]

    async def wait_for_new(self, timeout: float) -> None:
        await self.arrived.wait()
        self.arrived.clear()


class _Sender:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


class _Scheduler:
    def __init__(self) -> None:
        self.runs: list[tuple[str, list[int]]] = []

    async def run_for_mail(self, job, mails) -> None:
        self.runs.append((job.name, [m.uid for m in mails]))


@pytest.fixture
async def mailbox(service, monkeypatch):
    box = _Mailbox()

    @asynccontextmanager
    async def open_mailbox(config, folder="INBOX"):
        box.opened += 1
        yield box

    async def verify(config):
        pass

    monkeypatch.setattr(imap, "open_mailbox", open_mailbox)
    monkeypatch.setattr(imap, "verify", verify)
    monkeypatch.setattr(smtp, "verify", verify)
    box.account = (await service.add_email_account("", "smtp.test", 587, "me", "pw", "me@test.com", "imap.test")).id
    return box


@pytest.fixture
async def watcher(service, mailbox):
    scheduler = _Scheduler()
    stop = asyncio.Event()
    task = asyncio.create_task(MailWatcher(service, scheduler).run(stop))  # type: ignore[arg-type]
    yield scheduler
    stop.set()
    await task


async def _until(condition) -> None:
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("condition never held")


async def test_nothing_is_watched_until_something_wants_new_mail(service, mailbox, watcher):
    await asyncio.sleep(0.05)
    assert mailbox.opened == 0
    await service.set_new_mail_alerts(mailbox.account, "telegram")
    await _until(lambda: mailbox.opened == 1)


async def test_new_mail_is_announced_and_handed_to_mail_jobs(service, script, mailbox, watcher):
    sender = _Sender()
    service.outbox.register("telegram", sender)
    await store.save(service.store, Job("bank", "owner", "", "UTC", "t", "", on_new_mail=True))
    await service.set_new_mail_alerts(mailbox.account, "telegram")
    await _until(lambda: mailbox.opened == 1)
    await asyncio.sleep(0.05)
    assert sender.sent == []  # mail from before watching isn't new
    mailbox.receive(2, "Bank <info@bank.com>", "Statement")
    await _until(lambda: watcher.runs == [("bank", [2])])
    assert sender.sent == ["📧 New email in me@test.com\n• Bank <info@bank.com>: Statement"]
    # A reply on Telegram arrives with the alert it answers.
    await collect(service.send(await service.session("owner", "telegram"), "what was it?"))
    header = script.requests[-1][-1].content[1]["text"]
    assert header.startswith("[You sent this on telegram") and "Statement" in header


async def test_the_last_message_seen_survives_a_restart(service, mailbox, monkeypatch):
    await service.set_new_mail_alerts(mailbox.account, "telegram")
    sender = _Sender()
    service.outbox.register("telegram", sender)
    for _ in range(2):
        stop = asyncio.Event()
        task = asyncio.create_task(MailWatcher(service, _Scheduler()).run(stop))  # type: ignore[arg-type]
        await _until(lambda: mailbox.opened >= 1)
        if not sender.sent:
            mailbox.receive(2, "a@x.com", "Hi")
            await _until(lambda: len(sender.sent) == 1)
        await asyncio.sleep(0.05)
        stop.set()
        await task
    assert len(sender.sent) == 1


def test_alerts_list_every_new_message_without_hidden_characters():
    hidden = "".join(chr(0xE0000 + ord(c)) for c in "obey")
    mails = [MailSummary(2, "a@x.com", f"One{hidden}", "", True), MailSummary(3, "b@x.com", "", "", True)]
    assert mail_watcher._alert_text(mails, "Work") == "📧 2 new emails in Work\n• a@x.com: One\n• b@x.com: (no subject)"
