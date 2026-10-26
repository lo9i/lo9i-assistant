"""Checking each day once it has ended, without anyone asking: the daemon runs this as a supervised task. Ticks read
the wall clock, so a computer waking from sleep, or a daemon that wasn't running at midnight, checks the day before
within a tick. A daemon that was down for days checks each of them since the last day checked whole, oldest first
so each compares with the one before, and at most the KEPT_DAYS a report is kept for: their logs may still be
there (the starting context measured is today's). With no day checked before, only the day before."""

import asyncio
import contextlib
from datetime import UTC, date, datetime, timedelta

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
        for day in await self._unchecked(day_of(now) - timedelta(days=1)):
            await self._doctor.check(self._user_id, day, whole_day=True)

    async def _unchecked(self, yesterday: date) -> list[date]:
        """The days up to `yesterday` with no whole-day report, since the last day that has one."""
        reports = await records.reports(self._store, self._user_id)
        whole = {date.fromisoformat(r.day) for r in reports if r.whole_day}
        last = max((d for d in whole if d < yesterday), default=yesterday - timedelta(days=1))
        first = max(last + timedelta(days=1), yesterday - timedelta(days=records.KEPT_DAYS - 1))
        days = [first + timedelta(days=n) for n in range((yesterday - first).days + 1)]
        return [d for d in days if d not in whole]
