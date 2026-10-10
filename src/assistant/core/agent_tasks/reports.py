"""Which tasks started with start_task still have their end to tell, and the conversation that started
each (core/background.py). Kept in the Store, so a task that ends while the daemon is down is told when it
starts again.

The assistant may read a task's end itself (task_status, stop_task); then it isn't told again. A read and
the telling never overlap: the end waits while the assistant is reading the task, and a read waits while
the end is being told, so whichever comes second knows what the first did.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict

from langgraph.store.base import BaseStore

from assistant.core.background import Origin
from assistant.core.conversation import ended

_NAMESPACE = ("agent_task_reports",)


def note_key(task_id: str) -> str:
    """The task's turn header note (core/conversation/ended.py)."""
    return f"task:{task_id}"


class _Turn:
    """Who is reading a task now, and who is about to tell its end."""

    def __init__(self) -> None:
        self.readers = 0
        # Readers and the one telling its end: the turn is kept while anyone uses it.
        self.users = 0
        self.changed = asyncio.Condition()


class TaskReports:
    def __init__(self, store: BaseStore) -> None:
        self._store = store
        self._turns: dict[str, _Turn] = {}

    async def expect(self, task_id: str, origin: Origin) -> None:
        """The task was just started in `origin`: tell it when the task ends."""
        await self._store.aput(_NAMESPACE, task_id, asdict(origin))

    async def origin(self, task_id: str) -> Origin | None:
        """The conversation that started the task, while its end is still to be told."""
        item = await self._store.aget(_NAMESPACE, task_id)
        return Origin(**item.value) if item else None

    async def expected(self) -> list[str]:
        """The tasks whose end is still to be told."""
        return [item.key for item in await self._store.asearch(_NAMESPACE, limit=1000)]

    @asynccontextmanager
    async def reading(self, task_id: str) -> AsyncIterator[None]:
        """The assistant is reading the task's state (and may see its end, `seen`)."""
        with self._turn(task_id) as turn:
            async with turn.changed:
                turn.readers += 1
            try:
                yield
            finally:
                async with turn.changed:
                    turn.readers -= 1
                    turn.changed.notify_all()

    async def seen(self, task_id: str, reader: Origin | None) -> None:
        """The assistant saw how the task ended, in `reader`'s conversation: it needs no telling, and a
        note already waiting there is dropped."""
        await self._store.adelete(_NAMESPACE, task_id)
        if reader is not None:
            await ended.drop(self._store, reader.user_id, reader.thread_id, note_key(task_id))

    @asynccontextmanager
    async def ending(self, task_id: str) -> AsyncIterator[Origin | None]:
        """Once the assistant isn't reading the task: the conversation to tell of its end, or None when
        it needs no telling. Reads wait until this ends, so they find what was told. The task stays
        expected when telling it fails, to be told again."""
        with self._turn(task_id) as turn:
            async with turn.changed:
                await turn.changed.wait_for(lambda: not turn.readers)
                item = await self._store.aget(_NAMESPACE, task_id)
                yield Origin(**item.value) if item else None
                await self._store.adelete(_NAMESPACE, task_id)

    @contextmanager
    def _turn(self, task_id: str) -> Iterator[_Turn]:
        turn = self._turns.setdefault(task_id, _Turn())
        turn.users += 1
        try:
            yield turn
        finally:
            turn.users -= 1
            if not turn.users:
                del self._turns[task_id]
