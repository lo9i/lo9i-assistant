"""Waiting for a task to end: on any change in its folder (the worker writing its result or progress),
and again every few seconds for a worker that died without writing one."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from watchfiles import awatch

from assistant.core.agent_tasks.records import TaskState, TaskStore

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
    store: TaskStore, task_id: str, report: Report | None = None, measured: Measured | None = None
) -> TaskState:
    """The task's state once it's no longer running. `report`, when given, gets every progress line, and
    `measured` hears of each new context.json."""
    look = _Look(store, task_id, report, measured)
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


class _Look:
    """The task's state, after reporting the progress lines written since the last look and telling of a
    context the task wrote since."""

    def __init__(self, store: TaskStore, task_id: str, report: Report | None, measured: Measured | None) -> None:
        self._store, self._task_id, self._report, self._measured = store, task_id, report, measured
        self._seen = 0
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
