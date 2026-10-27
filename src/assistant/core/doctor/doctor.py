"""Checks a day: what went wrong, by cause, the starting context, and what changed since the day before."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Collection
from datetime import UTC, date, datetime

from langgraph.store.base import BaseStore

from assistant.core import notifications
from assistant.core.bus import EventBus
from assistant.core.doctor import changes, conversation_causes, log_causes, records
from assistant.core.doctor.causes import group
from assistant.core.doctor.clock import day_of
from assistant.core.doctor.context import PluginTools, starting_context
from assistant.core.doctor.conversation_causes import ConversationStates
from assistant.core.doctor.model import Cause, DoctorAlert, DoctorPage, DoctorReport, KnownCause

logger = logging.getLogger(__name__)


class Doctor:
    def __init__(
        self,
        store: BaseStore,
        bus: EventBus,
        states: Callable[[], ConversationStates],
        running: Callable[[], Collection[str]],
        plugins: PluginTools,
        window: Callable[[], Awaitable[int]],
    ) -> None:
        """`states`: the graph in use, which changes with the model. `running`: the conversations a run is on.
        `window`: the model's context window, which the starting context is measured against."""
        self._store = store
        self._bus = bus
        self._states = states
        self._running = running
        self._plugins = plugins
        self._window = window
        # The check the apps asked for, while it runs.
        self._checking: asyncio.Task | None = None

    async def page(self, user_id: str) -> DoctorPage:
        return DoctorPage(
            report=await records.latest(self._store, user_id),
            known=await records.known(self._store, user_id),
            checking=self._checking is not None,
        )

    async def check_now(self, user_id: str) -> DoctorPage:
        """Checks today so far in the background, unless a check runs; a `doctor` event tells when it's saved."""
        if self._checking is None:
            self._checking = asyncio.create_task(self._check_today(user_id))
            self._checking.add_done_callback(self._checked)
            self._bus.publish("doctor")
        return await self.page(user_id)

    async def wait(self) -> None:
        """Until the check the apps asked for ends, for tests."""
        if self._checking is not None:
            await asyncio.wait([self._checking])

    async def check(self, user_id: str, day: date, whole_day: bool) -> DoctorReport:
        """Checks `day`, keeps the report and tells it in the notifications feed."""
        previous = await records.before(self._store, user_id, day)
        report = await self._report(user_id, day, whole_day, previous)
        await records.save(self._store, user_id, report)
        ok = not changes.alerts(report)
        await notifications.add(
            self._store, user_id, "doctor", f"Health check of {day:%a %d %b}", changes.notification_text(report), ok
        )
        return report

    async def alerts(self, user_id: str) -> list[DoctorAlert]:
        """The latest report's, until dismissed."""
        report = await records.latest(self._store, user_id)
        return changes.alerts(report) if report else []

    async def dismiss(self, user_id: str, name: str) -> None:
        report = await records.latest(self._store, user_id)
        if report is not None and name not in report.dismissed:
            report.dismissed.append(name)
            await records.save(self._store, user_id, report)

    async def mark_known(self, user_id: str, cause_id: str) -> bool:
        """Leaves the cause out of reports from now on, and out of the latest one. False for a cause the latest
        report doesn't have."""
        report = await records.latest(self._store, user_id)
        cause = next((c for c in report.causes if c.id == cause_id), None) if report else None
        if report is None or cause is None:
            return False
        at = datetime.now(UTC).isoformat()
        known = KnownCause(id=cause.id, kind=cause.kind, title=cause.title, where=cause.where, at=at)
        await records.mark_known(self._store, user_id, known)
        report.causes = [c for c in report.causes if c.id != cause_id]
        report.known += 1
        await records.save(self._store, user_id, report)
        return True

    async def forget_known(self, user_id: str, cause_id: str) -> bool:
        """It shows again from the next check. False for a cause that wasn't marked."""
        forgotten = await records.forget_known(self._store, user_id, cause_id)
        if forgotten:
            self._bus.publish("doctor")
        return forgotten

    async def _check_today(self, user_id: str) -> None:
        await self.check(user_id, day_of(datetime.now(UTC)), whole_day=False)

    def _checked(self, task: asyncio.Task) -> None:
        self._checking = None
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.error("The health check failed", exc_info=error)
        self._bus.publish("doctor")

    async def _report(self, user_id: str, day: date, whole_day: bool, previous: DoctorReport | None) -> DoctorReport:
        found = await self._causes(user_id, day)
        known = {k.id for k in await records.known(self._store, user_id)}
        causes, gone = changes.compared([c for c in found if c.id not in known], previous)
        context = await starting_context(self._store, user_id, self._plugins, await self._window())
        same_day = await records.of_day(self._store, user_id, day)
        return DoctorReport(
            day=day.isoformat(),
            at=datetime.now(UTC).isoformat(),
            whole_day=whole_day,
            causes=causes,
            gone=[c for c in gone if c.id not in known],
            compared_with=previous.day if previous else "",
            context=changes.compared_context(context, previous),
            known=len(found) - len(causes),
            dismissed=same_day.dismissed if same_day else [],
        )

    async def _causes(self, user_id: str, day: date) -> list[Cause]:
        logged = await asyncio.to_thread(log_causes.day_occurrences, day)
        talks = await conversation_causes.day_occurrences(
            self._store, self._states(), user_id, day, set(self._running())
        )
        return [*group("log", logged), *group("conversation", talks)]
