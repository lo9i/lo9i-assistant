"""Watching the allowance: the daemon runs this as a supervised task. While the model provider is Copilot it checks
at start and every CHECK_HOURS after, keeps the result (records.py) and has Home's Copilot card built again from it.
Ticks read the wall clock, so a computer waking from sleep catches up within a tick. An alert that's due (alerts.py)
goes to the user's own chat on WhatsApp through the outbox, as send_message's do, once the channel is connected,
and is recorded for the turn header of their next message there (core/conversation/sent.py).

A failed check (GitHub unreachable, the token refused) is logged at INFO, not as a fault of the daemon's, so it
stays out of the health check; the card says it couldn't check."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
from langgraph.store.base import BaseStore

from assistant.core.conversation import sent as sent_messages
from assistant.core.copilot_quota import alerts, records
from assistant.core.copilot_quota.quota import QuotaCheckError, fetch
from assistant.core.llm.choice import ModelChoice
from assistant.core.outbox import DeliveryError, Outbox

logger = logging.getLogger(__name__)

CHECK_HOURS = 3
CHANNEL = "whatsapp"
_TICK_SECONDS = 60


class CopilotWatch:
    name = "copilot quota"

    def __init__(
        self,
        store: BaseStore,
        outbox: Outbox,
        model: Callable[[], ModelChoice],
        checked: Callable[[], Awaitable[None]],
        user_id: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """`model` gives the model in use; `checked` is called after each check (Home's card is built again).
        `transport` replaces the network in tests."""
        self._store = store
        self._outbox = outbox
        self._model = model
        self._checked = checked
        self._user_id = user_id
        self._transport = transport
        # In memory, so a daemon that starts checks at once.
        self._checked_at: datetime | None = None

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.tick(datetime.now(UTC))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=_TICK_SECONDS)

    async def tick(self, now: datetime) -> None:
        token = _token(self._model())
        if not token:
            return
        if self._checked_at is None or now - self._checked_at >= timedelta(hours=CHECK_HOURS):
            self._checked_at = now
            await self._check(token, now)
        await self._alert(now)

    async def _check(self, token: str, now: datetime) -> None:
        try:
            await records.save_check(self._store, now, await fetch(token, self._transport))
        except QuotaCheckError as e:
            logger.info("Couldn't check the Copilot allowance: %s", e)
            await records.save_check(self._store, now, None, str(e))
        await self._checked()

    async def _alert(self, now: datetime) -> None:
        """Sends the alert the last check calls for, once the channel can take it."""
        check = await records.last(self._store)
        if check is None or check.quota is None or CHANNEL not in self._outbox.channels:
            return
        sent = await records.sent(self._store)
        alert = alerts.due(check.quota, sent)
        if alert is None:
            return
        try:
            await self._outbox.send(CHANNEL, alert.text)
        except DeliveryError as e:
            logger.info("Couldn't send the Copilot alert on %s: %s", CHANNEL, e)
            return
        await records.save_sent(self._store, alerts.after(check.quota, sent, alert))
        await sent_messages.record(self._store, self._user_id, CHANNEL, alert.text, now)


def _token(model: ModelChoice) -> str:
    """The Copilot provider's GitHub token; "" with another provider."""
    return model.values.get("api_key", "") if model.provider == "copilot" else ""
