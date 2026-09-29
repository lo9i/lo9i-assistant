from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from assistant.core.agent.base import ServiceBase


class LockingMixin(ServiceBase):
    @asynccontextmanager
    async def _thread_lock(self, thread_id: str) -> AsyncIterator[None]:
        """One run per thread at a time, across all processes (Postgres advisory lock)."""
        async with self._memory.pool.connection() as conn:
            await conn.execute("SELECT pg_advisory_lock(hashtext(%s))", (thread_id,))
            try:
                yield
            finally:
                await conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (thread_id,))
