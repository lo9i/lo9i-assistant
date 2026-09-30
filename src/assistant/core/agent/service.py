import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from assistant.core import observability
from assistant.core.agent.locking import LockingMixin
from assistant.core.agent.memory import MemoryMixin
from assistant.core.agent.messaging import MessagingMixin
from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.telegram import TelegramMixin
from assistant.core.agent.threads import ThreadsMixin
from assistant.core.config import settings
from assistant.core.graph import build_graph
from assistant.core.speech.whisper import FasterWhisperTranscriber
from assistant.core.storage import Storage, open_storage


class AssistantService(ThreadsMixin, MemoryMixin, TelegramMixin, MessagingMixin, RunsMixin, LockingMixin):
    def __init__(self, storage: Storage, model: str):
        self._storage = storage
        self._graph = build_graph(storage, model)
        self._transcriber = FasterWhisperTranscriber()
        self._thread_locks = defaultdict(asyncio.Lock)

    @classmethod
    @asynccontextmanager
    async def open(cls, model: str | None = None) -> AsyncIterator["AssistantService"]:
        observability.init_tracing()
        try:
            async with open_storage(settings.database_path) as storage:
                yield cls(storage, model or settings.model)
        finally:
            observability.flush()
