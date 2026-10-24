"""Telling the conversation that started a task when the task ends (core/background.py). The daemon runs
it as a supervised task: it follows every task whose end is still to be told (reports.py), at start and
as start_task adds them, and tells each end unless the assistant has read it already. While it follows a
task, each step it takes is an `agent_task_progress` event, so the apps show what it's doing."""

import asyncio
import contextlib
import logging

from assistant.core.agent_tasks.records import TaskState, lost
from assistant.core.agent_tasks.reports import TaskReports, note_key
from assistant.core.agent_tasks.service import AgentTaskError, AgentTasks, FoundTask
from assistant.core.agent_tasks.steps import streamed
from assistant.core.agent_tasks.waiting import Report
from assistant.core.background import BackgroundEnds, Ended, short
from assistant.core.bus import EventBus
from assistant.core.waiting import first

logger = logging.getLogger(__name__)

# How much of what was asked, and of the result, the user's notification and the assistant's note show.
_ASKED_NOTICE, _RESULT_NOTICE = 60, 300
_ASKED_NOTE, _RESULT_NOTE = 200, 1_000
_LOST = "its worker ended without a result: the computer restarted or it was killed"


class TaskEnds:
    name = "task ends"

    def __init__(self, tasks: AgentTasks, reports: TaskReports, bus: EventBus, ends: BackgroundEnds) -> None:
        self._tasks = tasks
        self._reports = reports
        self._bus = bus
        self._ends = ends
        self._following: dict[str, asyncio.Task] = {}

    async def run(self, stop: asyncio.Event) -> None:
        try:
            while not stop.is_set():
                # Taken before reading, so a task added meanwhile is read again.
                after = self._bus.last_id
                await self._follow_expected()
                await first(stop.wait(), self._next_task(after))
        finally:
            await self._stop_following()

    async def _follow_expected(self) -> None:
        self._following = {task_id: f for task_id, f in self._following.items() if not f.done()}
        for task_id in await self._reports.expected():
            if task_id not in self._following:
                self._following[task_id] = asyncio.create_task(self._follow(task_id))

    async def _follow(self, task_id: str) -> None:
        try:
            found = await self._tasks.ended(task_id, self._progress(task_id))
        except AgentTaskError:
            # Its agent isn't installed now; it's followed again when a task is added or the daemon starts.
            return
        try:
            async with self._reports.ending(task_id) as origin:
                if origin is not None:
                    await self._ends.deliver(origin, ended(found))
        except Exception:
            logger.exception("Couldn't tell the end of task %s", task_id)

    def _progress(self, task_id: str) -> Report:
        """A step, not the words of one as they stream: those come again whole."""

        async def _report(message: str) -> None:
            if not streamed(message):
                self._bus.publish("agent_task_progress", task_id=task_id)

        return _report

    async def _next_task(self, after: int) -> None:
        async for event in self._bus.subscribe(after):
            if event.kind == "agent_task_reports":
                return

    async def _stop_following(self) -> None:
        for following in self._following.values():
            following.cancel()
        for following in self._following.values():
            with contextlib.suppress(asyncio.CancelledError):
                await following
        self._following = {}


def ended(found: FoundTask) -> Ended:
    state, agent = found.state, found.agent.name
    task = state.task
    result = _result(state)
    notice = _notice(agent, state, short(task.prompt, _ASKED_NOTICE), short(result, _RESULT_NOTICE))
    asked = short(task.prompt, _ASKED_NOTE)
    note = f'{agent}\'s task {task.id} in {task.repository}, asked "{asked}", is {state.status}'
    if result:
        note += f": {short(result, _RESULT_NOTE)}"
    return Ended(note_key(task.id), state.status == "done", notice, note, plugin=found.agent.server)


def _notice(agent: str, state: TaskState, asked: str, result: str) -> str:
    task = f"task {state.task.id} ({asked})"
    if state.status == "done":
        return f"✅ {agent} finished {task}: {result}"
    if state.status == "stopped":
        return f"⏹️ {agent}'s {task} was stopped."
    return f"⚠️ {agent}'s {task} failed: {result}"


def _result(state: TaskState) -> str:
    if lost(state):
        return _LOST
    return state.outcome.text.strip() if state.outcome else ""
