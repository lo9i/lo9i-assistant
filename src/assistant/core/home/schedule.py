"""Keeping Home current without anyone asking: the daemon runs this as a supervised task. Home is refreshed on the
first tick of the user's day, so today's sections are ready before the first visit, and every WATCHED_MINUTES
while a client shows it (the web app says so while its Home tab is visible, and the daemon forgets a client that
disconnects). Ticks read the wall clock, so a computer waking from sleep catches up within a tick.

While a client shows it, the Conversations card, built by code without the model (conversations.py), is built again
each time a conversation changes, so the times it shows keep up with them; the Open loops card (loops.py) each time
the loops change."""

import asyncio
import contextlib
from datetime import UTC, datetime

from langgraph.store.base import BaseStore

from assistant.core.bus import EventBus
from assistant.core.home import results, sections
from assistant.core.home.clock import day_of, within
from assistant.core.home.refresh import HomeRefresh
from assistant.core.waiting import first

WATCHED_MINUTES = 30
_TICK_SECONDS = 30
# The cards built by code that are built again while a client shows Home, by the event that changes them.
_FOLLOWED = {"conversations": sections.CONVERSATIONS, "proactive": sections.LOOPS}


class HomeSchedule:
    name = "home"

    def __init__(self, store: BaseStore, refresh: HomeRefresh, user_id: str, bus: EventBus) -> None:
        self._store = store
        self._refresh = refresh
        self._user_id = user_id
        self._bus = bus
        # The clients showing Home now.
        self._watchers: set[str] = set()

    def watch(self, client_id: str) -> None:
        if client_id:
            self._watchers.add(client_id)

    def unwatch(self, client_id: str) -> None:
        self._watchers.discard(client_id)

    async def run(self, stop: asyncio.Event) -> None:
        await first(self._ticking(stop), self._following(self._bus.last_id))

    async def _ticking(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.tick(datetime.now(UTC))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=_TICK_SECONDS)

    async def _following(self, after: int) -> None:
        async for event in self._bus.subscribe(after):
            if event.kind in _FOLLOWED and self._watchers:
                await self._refresh.refresh(self._user_id, only=[_FOLLOWED[event.kind]])

    async def tick(self, now: datetime) -> None:
        if await self._due(now):
            await self._refresh.refresh(self._user_id, force=True)

    async def _due(self, now: datetime) -> bool:
        refreshed = await results.refreshed_at(self._store, self._user_id)
        if refreshed is None or day_of(refreshed) != day_of(now):
            return True
        return bool(self._watchers) and not within(refreshed, now, WATCHED_MINUTES)
