"""Runs outlive the request that started them. Events are buffered per run, so a client that
disconnects, or a second client, can replay them by id and then follow along live."""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from assistant.core.events import Error, Event
from assistant.protocol import event_to_dict

logger = logging.getLogger(__name__)

# Finished runs stay replayable this long.
_KEEP_SECONDS = 600


@dataclass
class Run:
    id: str
    thread_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)


class RunHub:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._tasks: set[asyncio.Task] = set()

    def start(self, thread_id: str, events: AsyncIterator[Event]) -> Run:
        run = Run(id=uuid4().hex, thread_id=thread_id)
        self._runs[run.id] = run
        task = asyncio.create_task(self._consume(run, events))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    async def follow(self, run: Run, after: int) -> AsyncIterator[tuple[int, dict[str, Any] | None]]:
        """(event id, event) for events after `after`, then (id, None) once the run is finished."""
        index = after
        while True:
            async with run.changed:
                await run.changed.wait_for(lambda: len(run.events) > index or run.finished)
                pending, finished = run.events[index:], run.finished
            for event in pending:
                index += 1
                yield index, event
            if finished and index >= len(run.events):
                yield index + 1, None
                return

    async def _consume(self, run: Run, events: AsyncIterator[Event]) -> None:
        try:
            async for event in events:
                await self._append(run, event_to_dict(event))
        except Exception as e:
            logger.exception("Run %s failed", run.id)
            await self._append(run, event_to_dict(Error(f"{type(e).__name__}: {e}")))
        finally:
            async with run.changed:
                run.finished = True
                run.changed.notify_all()
            asyncio.get_running_loop().call_later(_KEEP_SECONDS, self._runs.pop, run.id, None)

    @staticmethod
    async def _append(run: Run, event: dict[str, Any]) -> None:
        async with run.changed:
            run.events.append(event)
            run.changed.notify_all()
