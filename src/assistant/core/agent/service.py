from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from assistant.core import observability
from assistant.core.agent.locking import LockingMixin
from assistant.core.agent.messaging import MessagingMixin
from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.threads import ThreadsMixin
from assistant.core.config import settings
from assistant.core.graph import build_graph
from assistant.core.memory import Memory, open_memory


class AssistantService(ThreadsMixin, MessagingMixin, RunsMixin, LockingMixin):
    def __init__(self, memory: Memory, model: str):
        self._memory = memory
        self._graph = build_graph(memory, model)

    @classmethod
    @asynccontextmanager
    async def open(cls, model: str | None = None) -> AsyncIterator["AssistantService"]:
        observability.init_tracing()
        try:
            async with open_memory(settings.database_url) as memory:
                yield cls(memory, model or settings.model)
        finally:
            observability.flush()
