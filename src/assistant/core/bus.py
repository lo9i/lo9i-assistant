"""In-process event bus: components publish what changed, and every connected client hears it.

Events carry an increasing id and a short history is kept, so a client that reconnects can replay
what it missed. Slow subscribers drop events rather than slowing the daemon down.
"""

import asyncio
import itertools
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

_HISTORY = 500
_QUEUE = 1000


@dataclass(frozen=True)
class BusEvent:
    id: int
    kind: str
    data: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self._history: deque[BusEvent] = deque(maxlen=_HISTORY)
        self._subscribers: set[asyncio.Queue[BusEvent]] = set()

    def publish(self, kind: str, **data: Any) -> None:
        event = BusEvent(next(self._ids), kind, data)
        self._history.append(event)
        for queue in list(self._subscribers):
            if queue.full():
                continue
            queue.put_nowait(event)

    async def subscribe(self, after: int = 0) -> AsyncIterator[BusEvent]:
        """Events with id greater than `after`: missed ones from history first, then live ones."""
        queue: asyncio.Queue[BusEvent] = asyncio.Queue(maxsize=_QUEUE)
        self._subscribers.add(queue)
        try:
            last = after
            for event in [e for e in self._history if e.id > after]:
                last = event.id
                yield event
            while True:
                event = await queue.get()
                if event.id > last:
                    last = event.id
                    yield event
        finally:
            self._subscribers.discard(queue)
