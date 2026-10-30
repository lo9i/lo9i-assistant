"""The runs a client follows over its /events stream, instead of a stream of their own (/runs/<id>/events).

A browser speaks HTTP/1.1 to a plain-HTTP origin (localhost) and keeps at most six connections open to it, across
all its tabs. A stream per run followed and one per tab used them up, and every other request of the page waited
for one to close. So the web app follows each run under an id of its own (`follow`), and the run's events go down
its client's open /events stream: `run_events` with how many of the run's events came before them, which a client
that asked again after a reconnection uses to drop what it already has, and `run_end` after its last.

A client asks again for what it follows each time its stream opens, from where it got to. A stream that closes
stops sending; what it followed is forgotten once no stream of that client opens within `_GRACE_SECONDS`."""

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from typing import Any

from assistant.daemon.runs import Run, RunHub

# A client's stream: (device id, client id). A device follows runs only on its own streams.
type StreamKey = tuple[str, str]
type Sent = dict[str, Any]

RUN_EVENTS = "run_events"
RUN_END = "run_end"
_GRACE_SECONDS = 60


@dataclass
class _Follow:
    run: Run
    after: int
    task: asyncio.Task[None] | None = None


class RunFollows:
    def __init__(self, hub: RunHub, grace_seconds: float = _GRACE_SECONDS) -> None:
        self._hub = hub
        self._grace_seconds = grace_seconds
        self._follows: dict[StreamKey, dict[str, _Follow]] = {}
        # The stream each client reads now; a newer one replaces it.
        self._streams: dict[StreamKey, asyncio.Queue[Sent]] = {}

    def follow(self, key: StreamKey, follow_id: str, run: Run, after: int) -> None:
        """Sends the run's events after `after` down the client's stream, now or once it opens. Asking again under
        the same id starts again from `after`."""
        self.stop(key, follow_id)
        follow = _Follow(run, after)
        self._follows.setdefault(key, {})[follow_id] = follow
        if (queue := self._streams.get(key)) is not None:
            self._start(key, follow_id, follow, queue)

    def stop(self, key: StreamKey, follow_id: str) -> None:
        follow = self._follows.get(key, {}).pop(follow_id, None)
        if follow is not None and follow.task is not None:
            follow.task.cancel()

    async def events(self, key: StreamKey, bus: AsyncIterator[Sent]) -> AsyncGenerator[Sent]:
        """The client's bus events with the events of the runs it follows, for as long as it reads them."""
        with self._stream(key) as queue:
            pump = asyncio.create_task(_pump(bus, queue))
            try:
                while True:
                    yield await _next(queue, pump)
            finally:
                pump.cancel()

    @contextlib.contextmanager
    def _stream(self, key: StreamKey):
        queue: asyncio.Queue[Sent] = asyncio.Queue()
        self._cancel_tasks(key)
        self._streams[key] = queue
        for follow_id, follow in self._follows.get(key, {}).items():
            self._start(key, follow_id, follow, queue)
        try:
            yield queue
        finally:
            self._closed(key, queue)

    def _closed(self, key: StreamKey, queue: asyncio.Queue[Sent]) -> None:
        """An older stream noticed closing after its client opened a new one leaves the new one be."""
        if self._streams.get(key) is not queue:
            return
        del self._streams[key]
        self._cancel_tasks(key)
        asyncio.get_running_loop().call_later(self._grace_seconds, self._forget_if_away, key)

    def _forget_if_away(self, key: StreamKey) -> None:
        if key not in self._streams:
            self._follows.pop(key, None)

    def _start(self, key: StreamKey, follow_id: str, follow: _Follow, queue: asyncio.Queue[Sent]) -> None:
        follow.task = asyncio.create_task(self._send(key, follow_id, follow, queue))

    async def _send(self, key: StreamKey, follow_id: str, follow: _Follow, queue: asyncio.Queue[Sent]) -> None:
        async for after, events, finished in self._hub.batches(follow.run, follow.after):
            if events:
                queue.put_nowait(_sent(RUN_EVENTS, follow=follow_id, after=after, events=events))
            if finished:
                queue.put_nowait(_sent(RUN_END, follow=follow_id))
        follows = self._follows.get(key, {})
        if follows.get(follow_id) is follow:
            del follows[follow_id]

    def _cancel_tasks(self, key: StreamKey) -> None:
        for follow in self._follows.get(key, {}).values():
            if follow.task is not None:
                follow.task.cancel()
                follow.task = None


async def _pump(events: AsyncIterator[Sent], queue: asyncio.Queue[Sent]) -> None:
    async for event in events:
        queue.put_nowait(event)


async def _next(queue: asyncio.Queue[Sent], pump: asyncio.Task[None]) -> Sent:
    """The next event, or the bus's error if it failed, which ends the stream."""
    getting = asyncio.ensure_future(queue.get())
    await asyncio.wait({getting, pump}, return_when=asyncio.FIRST_COMPLETED)
    if getting.done():
        return getting.result()
    getting.cancel()
    pump.result()
    raise RuntimeError("The bus stopped")


def _sent(kind: str, **data: Any) -> Sent:
    """Without an id: a client resumes the bus after the last bus event it got, and asks for its runs again."""
    return {"event": kind, "data": json.dumps(data)}
