"""Reminders of open loops at their time (`remind_at`): the urgent ones, which can't wait for the next briefing. Sent
only between the briefing time and the nightly time, and at most PER_DAY a day, so the user isn't woken up or flooded:
one that comes outside those waits for the next morning, and those past the day's count wait for the next day; the
briefing lists every open loop meanwhile. A loop of a kind the user muted isn't reminded of."""

from datetime import datetime

from langgraph.store.base import BaseStore

from assistant.core import i18n
from assistant.core.proactive import clock, loops, records
from assistant.core.proactive.model import OpenLoop, ProactiveSettings
from assistant.core.proactive.telling import Teller

PER_DAY = 3


class Reminders:
    def __init__(self, store: BaseStore, teller: Teller, user_id: str) -> None:
        self._store = store
        self._teller = teller
        self._user_id = user_id

    async def send_due(self, now: datetime, chosen: ProactiveSettings) -> int:
        """How many were sent."""
        if not chosen.reminders or not clock.within_day(now, chosen.briefing_time, chosen.nightly_time):
            return 0
        day, sent = clock.day_of(now), 0
        for loop in await loops.due_reminders(self._store, self._user_id, now):
            if loop.kind in chosen.muted:
                await loops.mark_reminded(self._store, self._user_id, loop, now)
                continue
            if await records.reminded_on(self._store, self._user_id, day) >= PER_DAY:
                break
            await self._remind(loop, now, day)
            sent += 1
        return sent

    async def _remind(self, loop: OpenLoop, now: datetime, day: str) -> None:
        t = await i18n.chosen(self._store)
        due = t(" (due {day})", day=loop.due) if loop.due else ""
        await self._teller.tell("reminder", t("Reminder"), t("Reminder: {text}", text=loop.text) + due)
        await loops.mark_reminded(self._store, self._user_id, loop, now)
        await records.count_reminder(self._store, self._user_id, day)
