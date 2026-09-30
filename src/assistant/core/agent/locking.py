import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from assistant.core.agent.base import ServiceBase


class LockingMixin(ServiceBase):
    """One run per thread at a time. The daemon is the only process running the agent,
    so an in-process lock per thread is enough."""

    _thread_locks: defaultdict[str, asyncio.Lock]

    @asynccontextmanager
    async def _thread_lock(self, thread_id: str) -> AsyncIterator[None]:
        async with self._thread_locks[thread_id]:
            yield
