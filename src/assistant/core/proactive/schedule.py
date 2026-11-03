"""Running the briefing and the reviews without anyone asking: the daemon runs ProactiveSchedule as a supervised task.
Ticks read the wall clock, so a computer waking from sleep catches up within a tick: the briefing up to CATCH_UP_HOURS
after its time (later, the day goes without it), the nightly review until the day ends, and the weekly one after the
nightly review of its day. Each runs once a day, in the background (ProactiveRuns), whatever came of it; the apps
start one now too ("Brief me now"). Reminders of open loops go out as they come due (reminders.py)."""

import asyncio
import contextlib
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from langgraph.store.base import BaseStore

from assistant.core.bus import EventBus
from assistant.core.proactive import clock, records
from assistant.core.proactive.briefing import Briefer
from assistant.core.proactive.model import Briefing, ProactiveSettings, Review
from assistant.core.proactive.reminders import Reminders
from assistant.core.proactive.review import Reviewer

Work = Literal["briefing", "nightly", "weekly"]
CATCH_UP_HOURS = 6
_TICK_SECONDS = 60


class ProactiveRuns:
    """The briefing and the reviews running now, one of each at a time, each publishing `proactive` as it starts and
    ends."""

    def __init__(self, bus: EventBus, briefer: Briefer, reviewer: Reviewer) -> None:
        self._bus = bus
        self._briefer = briefer
        self._reviewer = reviewer
        self._running: dict[Work, asyncio.Task] = {}

    @property
    def running(self) -> list[Work]:
        return sorted(self._running)

    def start(self, work: Work, now: datetime) -> bool:
        """False when it runs already."""
        if work in self._running:
            return False
        task = asyncio.create_task(self._done(work, now))
        self._running[work] = task
        task.add_done_callback(lambda _: self._ended(work))
        self._bus.publish("proactive")
        return True

    async def wait(self) -> None:
        """Until none runs, for tests and callers that need the result."""
        while self._running:
            await asyncio.wait(list(self._running.values()))

    def cancel(self) -> None:
        for task in self._running.values():
            task.cancel()

    def _done(self, work: Work, now: datetime) -> Coroutine[Any, Any, Briefing | Review]:
        return self._briefer.brief(now) if work == "briefing" else self._reviewer.review(work, now)

    def _ended(self, work: Work) -> None:
        self._running.pop(work, None)
        self._bus.publish("proactive")


class ProactiveSchedule:
    name = "proactive"

    def __init__(self, store: BaseStore, runs: ProactiveRuns, reminders: Reminders, user_id: str) -> None:
        self._store = store
        self._runs = runs
        self._reminders = reminders
        self._user_id = user_id

    async def run(self, stop: asyncio.Event) -> None:
        try:
            while not stop.is_set():
                await self.tick(datetime.now(UTC))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=_TICK_SECONDS)
        finally:
            self._runs.cancel()

    async def tick(self, now: datetime) -> None:
        chosen = await records.load_settings(self._store, self._user_id)
        for work in await self._due(now, chosen):
            self._runs.start(work, now)
        await self._reminders.send_due(now, chosen)

    async def _due(self, now: datetime, chosen: ProactiveSettings) -> list[Work]:
        today, running = clock.day_of(now), self._runs.running
        briefing = await records.latest_briefing(self._store, self._user_id)
        reviewed = {r.kind for r in await records.reviews(self._store, self._user_id) if r.day == today}
        due: list[Work] = []
        if chosen.briefing and (briefing is None or briefing.day != today) and briefing_time(now, chosen):
            due.append("briefing")
        if chosen.nightly and "nightly" not in reviewed and _past(now, chosen.nightly_time):
            due.append("nightly")
        elif _weekly_due(now, chosen, reviewed) and "nightly" not in running:
            due.append("weekly")
        return [w for w in due if w not in running]


def briefing_time(now: datetime, chosen: ProactiveSettings) -> bool:
    """From the briefing time to CATCH_UP_HOURS after it, on the user's day."""
    starts = clock.at(clock.local(now).date(), chosen.briefing_time)
    return starts <= now < starts + timedelta(hours=CATCH_UP_HOURS)


def _past(now: datetime, hhmm: str) -> bool:
    return now >= clock.at(clock.local(now).date(), hhmm)


def _weekly_due(now: datetime, chosen: ProactiveSettings, reviewed: set[str]) -> bool:
    """On its day, after that day's nightly review, or from the nightly time when that's off."""
    if not chosen.weekly or "weekly" in reviewed or clock.local(now).weekday() != chosen.weekly_day:
        return False
    return "nightly" in reviewed if chosen.nightly else _past(now, chosen.nightly_time)
