"""Waiting for a task to end: on any change in its folder (the worker writing its result or progress),
and again every few seconds for a worker that died without writing one."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from watchfiles import awatch

from lo9i.core.agent_tasks.records import TaskState, TaskStore

# How often a wait looks again without a file change: it misses no change made just before it began.
_RECHECK_MS = 2_000
# Changes are read at most this long after they're written: a streamed reply's words flow, not in bursts.
_DEBOUNCE_MS = 100

# watchfiles logs every change it sees at INFO, which would fill the log while a task is followed.
logging.getLogger("watchfiles").setLevel(logging.WARNING)

# Gets each progress line of a task as it's written.
Report = Callable[[str], Awaitable[None]]
# Told each time the task writes how full the agent's context is.
Measured = Callable[[], None]


async def until_ended(
    store: TaskStore, task_id: str, report: Report | None = None, measured: Measured | None = None, seen: int = 0
) -> TaskState:
    """The task's state once it's no longer running. `report`, when given, gets every progress line after the first
    `seen`, and `measured` hears of each new context.json."""
    look = _Look(store, task_id, report, measured, seen)
    if (state := await look()).status != "running":
        return state
    folder = store.folder(task_id)
    async for _ in awatch(folder, yield_on_timeout=True, rust_timeout=_RECHECK_MS, debounce=_DEBOUNCE_MS, step=20):
        if (state := await look()).status != "running":
            return state
    return await look()


async def at_most(store: TaskStore, task_id: str, seconds: int, report: Report | None = None) -> None:
    """Until the task ends or `seconds` pass. `report`, when given, gets every progress line."""
    try:
        async with asyncio.timeout(seconds):
            await until_ended(store, task_id, report)
    except TimeoutError:
        return


async def withdrawal(store: TaskStore, task_id: str, message_id: str, seconds: float) -> bool | None:
    """Whether the worker took back the message sent under `message_id` (TaskStore.withdrawal): True once it did, False
    once the agent took it or the task ended without either; None when `seconds` pass first."""
    try:
        async with asyncio.timeout(seconds):
            return await _until_withdrawn(store, task_id, message_id)
    except TimeoutError:
        return None


async def _until_withdrawn(store: TaskStore, task_id: str, message_id: str) -> bool:
    async def look() -> bool | None:
        if (found := await asyncio.to_thread(store.withdrawal, task_id, message_id)) is not None:
            return found
        state = await asyncio.to_thread(store.state, task_id, 0)
        return None if state.status == "running" else False

    if (found := await look()) is not None:
        return found
    async for _ in awatch(store.folder(task_id), yield_on_timeout=True, rust_timeout=_RECHECK_MS, step=20):
        if (found := await look()) is not None:
            return found
    return False


class _Look:
    """The task's state, after reporting the progress lines written since the last look and telling of a
    context the task wrote since."""

    def __init__(
        self, store: TaskStore, task_id: str, report: Report | None, measured: Measured | None, seen: int = 0
    ) -> None:
        self._store, self._task_id, self._report, self._measured = store, task_id, report, measured
        self._seen = seen
        self._measured_at = 0

    async def __call__(self) -> TaskState:
        if self._report is not None:
            for line in await asyncio.to_thread(self._store.progress_after, self._task_id, self._seen):
                self._seen += 1
                await self._report(line)
        if self._measured is not None:
            await self._tell_measured(self._measured)
        return await asyncio.to_thread(self._store.state, self._task_id)

    async def _tell_measured(self, measured: Measured) -> None:
        written = await asyncio.to_thread(self._store.context_written, self._task_id)
        if written != self._measured_at:
            self._measured_at = written
            measured()
