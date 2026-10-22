"""Keeping Home current without anyone asking: the daemon runs this as a supervised task. Home is refreshed on the
first tick of the user's day, so today's sections are ready before the first visit, and every WATCHED_MINUTES
while a client shows it (the web app says so while its Home tab is visible, and the daemon forgets a client that
disconnects). Ticks read the wall clock, so a computer waking from sleep catches up within a tick."""

import asyncio
import contextlib
from datetime import UTC, datetime

from langgraph.store.base import BaseStore

from assistant.core.home import results
from assistant.core.home.clock import day_of, within
from assistant.core.home.refresh import HomeRefresh

WATCHED_MINUTES = 30
_TICK_SECONDS = 30


class HomeSchedule:
    name = "home"

    def __init__(self, store: BaseStore, refresh: HomeRefresh, user_id: str) -> None:
        self._store = store
        self._refresh = refresh
        self._user_id = user_id
        # The clients showing Home now.
        self._watchers: set[str] = set()

    def watch(self, client_id: str) -> None:
        if client_id:
            self._watchers.add(client_id)

    def unwatch(self, client_id: str) -> None:
        self._watchers.discard(client_id)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.tick(datetime.now(UTC))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=_TICK_SECONDS)

    async def tick(self, now: datetime) -> None:
        if await self._due(now):
            await self._refresh.refresh(self._user_id, force=True)

    async def _due(self, now: datetime) -> bool:
        refreshed = await results.refreshed_at(self._store, self._user_id)
        if refreshed is None or day_of(refreshed) != day_of(now):
            return True
        return bool(self._watchers) and not within(refreshed, now, WATCHED_MINUTES)
