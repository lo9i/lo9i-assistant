"""Checks the extras for newer plugin versions in the background: when the daemon starts, then once a
day, and right away when checks are turned back on. A check reads the extras' latest commit and
downloads them only when it changed (contents.py); a new listing publishes `plugins`, so clients
update what they show."""

import asyncio
import logging

from langgraph.store.base import BaseStore

from assistant.core.bus import EventBus
from assistant.core.repositories import contents, updates
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.known import EXTRAS
from assistant.core.waiting import first

logger = logging.getLogger(__name__)

CHECK_SECONDS = 24 * 60 * 60


class UpdateChecker:
    name = "plugin updates"

    def __init__(self, store: BaseStore, bus: EventBus) -> None:
        self._store = store
        self._bus = bus

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
        try:
            await contents.browse(self._store, EXTRAS)
        except RepositoryError as e:
            logger.warning("Couldn't check the extras for plugin updates: %s", e)

    async def _turned_on(self, after: int) -> None:
        async for event in self._bus.subscribe(after):
            if event.kind == "settings" and await updates.checks_enabled(self._store):
                return
