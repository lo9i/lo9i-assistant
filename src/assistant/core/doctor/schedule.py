"""Checking each day once it has ended, without anyone asking: the daemon runs this as a supervised task. Ticks read
the wall clock, so a computer waking from sleep, or a daemon that wasn't running at midnight, checks the day before
within a tick. Only the day before: older days' logs may have rotated away, and the starting context is today's."""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

from langgraph.store.base import BaseStore

from assistant.core.doctor import records
from assistant.core.doctor.clock import day_of
from assistant.core.doctor.doctor import Doctor

_TICK_SECONDS = 60


class DoctorSchedule:
    name = "doctor"

    def __init__(self, store: BaseStore, doctor: Doctor, user_id: str) -> None:
        self._store = store
        self._doctor = doctor
        self._user_id = user_id

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.tick(datetime.now(UTC))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=_TICK_SECONDS)

    async def tick(self, now: datetime) -> None:
        yesterday = day_of(now) - timedelta(days=1)
        checked = await records.of_day(self._store, self._user_id, yesterday)
        if checked is None or not checked.whole_day:
            await self._doctor.check(self._user_id, yesterday, whole_day=True)
