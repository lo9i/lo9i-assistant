"""Checks the listed repositories (the extras and the ones the user added, listed.py) for newer plugin
versions in the background: when the daemon starts, then once a day, and right away when checks are
turned back on. A check reads each one's latest commit and downloads it only when it changed
(contents.py); a new listing publishes `plugins`, so clients update what they show."""

import asyncio
import logging

from langgraph.store.base import BaseStore

from assistant.core.bus import EventBus
from assistant.core.repositories import listed, updates
from assistant.core.secret_store import SecretBox
from assistant.core.waiting import first

logger = logging.getLogger(__name__)

CHECK_SECONDS = 24 * 60 * 60


class UpdateChecker:
    name = "plugin updates"

    def __init__(self, store: BaseStore, bus: EventBus, secrets: SecretBox) -> None:
        self._store = store
        self._bus = bus
        # Private repositories are read with their tokens.
        self._secrets = secrets

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            after = self._bus.last_id
            if await updates.checks_enabled(self._store):
                await self._check()
                await first(stop.wait(), asyncio.sleep(CHECK_SECONDS))
            else:
                await first(stop.wait(), self._turned_on(after))

    async def _check(self) -> None:
        """An unreachable repository waits for the next check."""
        for read in await listed.plugins(self._store, self._secrets):
            if read.error:
                logger.warning("Couldn't check %s for plugin updates: %s", read.repository.name, read.error)

    async def _turned_on(self, after: int) -> None:
        async for event in self._bus.subscribe(after):
            if event.kind == "settings" and await updates.checks_enabled(self._store):
                return
