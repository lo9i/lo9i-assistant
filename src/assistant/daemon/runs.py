"""Runs outlive the request that started them. Events are buffered per run, so a client that
disconnects, or a second client, can replay them by id and then follow along live."""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import partial
from typing import Any
from uuid import uuid4

from assistant.core.bus import EventBus
from assistant.core.events import Error, Event, TextDelta
from assistant.protocol import event_to_dict

logger = logging.getLogger(__name__)

# Finished runs stay replayable this long.
_KEEP_SECONDS = 600
# Reply characters included when a run's end is announced.
_EXCERPT = 300


@dataclass
class Run:
    id: str
    thread_id: str
    channel: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)


class RunHub:
    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        self._runs: dict[str, Run] = {}
        self._tasks: set[asyncio.Task] = set()

    def start(self, thread_id: str, events: AsyncIterator[Event], channel: str = "", text: str = "") -> Run:
        """Start consuming a run. Other clients hear about it on the bus, so a conversation shown
        in several places (terminal, Telegram) updates everywhere."""
        run = Run(id=uuid4().hex, thread_id=thread_id, channel=channel)
        self._runs[run.id] = run
        if self._bus is not None:
            self._bus.publish("run", run_id=run.id, thread_id=thread_id, channel=channel, text=text)
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
                await run.changed.wait_for(partial(_has_news, run, index))
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
            self._announce_finished(run)
            asyncio.get_running_loop().call_later(_KEEP_SECONDS, self._runs.pop, run.id, None)

    def _announce_finished(self, run: Run) -> None:
        """Lets clients that stopped watching (for example after /new) know the run is done."""
        if self._bus is None:
            return
        failed = any(e["type"] == Error.__name__ for e in run.events)
        reply = "".join(e["text"] for e in run.events if e["type"] == TextDelta.__name__).strip()
        self._bus.publish(
            "run_finished",
            run_id=run.id,
            thread_id=run.thread_id,
            channel=run.channel,
            status="failed" if failed else "ok",
            reply=reply[-_EXCERPT:],
        )

    @staticmethod
    async def _append(run: Run, event: dict[str, Any]) -> None:
        async with run.changed:
            run.events.append(event)
            run.changed.notify_all()


def _has_news(run: Run, seen: int) -> bool:
    return len(run.events) > seen or run.finished
