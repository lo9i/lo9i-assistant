"""Approvals for runs nobody is watching (scheduled jobs), answered on a channel the user carries.

A channel adapter registers a forwarder while it can deliver (Telegram), like the outbox. A job
run that needs approval pauses; the scheduler asks here, the forwarder shows the request with
Approve and Reject buttons, and the adapter passes the answer back with `answer`. With no
forwarder registered, unattended runs deny instead (`tools/approval.py`).
"""

import asyncio
import contextlib
import logging
from typing import Any, Protocol

from assistant.core.outbox import DeliveryError

logger = logging.getLogger(__name__)

Decision = dict[str, Any]


class Forwarder(Protocol):
    async def forward(self, interrupt_id: str, title: str, request: dict[str, Any]) -> None:
        """Show the request to the user with buttons that answer it. Raises DeliveryError."""
        ...


class RemoteApprovals:
    def __init__(self) -> None:
        self._forwarders: dict[str, Forwarder] = {}
        self._waiting: dict[str, asyncio.Future[Decision]] = {}
        self._available = asyncio.Event()

    def register(self, channel: str, forwarder: Forwarder) -> None:
        self._forwarders[channel] = forwarder
        self._available.set()

    def unregister(self, channel: str) -> None:
        self._forwarders.pop(channel, None)
        if not self._forwarders:
            self._available.clear()

    @property
    def available(self) -> bool:
        return bool(self._forwarders)

    async def wait_available(self, timeout: float) -> bool:
        """Wait until a channel can forward requests. False when none could within `timeout`."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._available.wait(), timeout)
        return self.available

    async def ask(self, interrupt_id: str, title: str, request: dict[str, Any], timeout: float) -> Decision | None:
        """The user's decision, or None when no channel took the request or nobody answered in time."""
        waiting: asyncio.Future[Decision] = asyncio.get_running_loop().create_future()
        self._waiting[interrupt_id] = waiting
        try:
            if not await self._forward(interrupt_id, title, request):
                return None
            with contextlib.suppress(TimeoutError):
                return await asyncio.wait_for(waiting, timeout)
            return None
        finally:
            self._waiting.pop(interrupt_id, None)

    def answer(self, interrupt_id: str, decision: Decision) -> bool:
        """Pass on a decision. False when that request isn't waiting any more."""
        waiting = self._waiting.get(interrupt_id)
        if waiting is None or waiting.done():
            return False
        waiting.set_result(decision)
        return True

    async def _forward(self, interrupt_id: str, title: str, request: dict[str, Any]) -> bool:
        delivered = False
        for channel, forwarder in list(self._forwarders.items()):
            try:
                await forwarder.forward(interrupt_id, title, request)
                delivered = True
            except DeliveryError as e:
                logger.warning("Couldn't forward an approval on %s: %s", channel, e)
        return delivered
