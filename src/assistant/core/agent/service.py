import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from assistant.core import observability
from assistant.core.agent.archive import ArchiveMixin
from assistant.core.agent.email import EmailMixin
from assistant.core.agent.identity import IdentityMixin
from assistant.core.agent.jobs import JobsMixin
from assistant.core.agent.locking import LockingMixin
from assistant.core.agent.memory import MemoryMixin
from assistant.core.agent.messaging import MessagingMixin
from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.skills import SkillsMixin
from assistant.core.agent.telegram import TelegramMixin
from assistant.core.agent.threads import ThreadsMixin
from assistant.core.agent.usage import UsageMixin
from assistant.core.bus import EventBus
from assistant.core.config import settings
from assistant.core.conversation.digest import build_digester
from assistant.core.graph import build_graph
from assistant.core.outbox import Outbox
from assistant.core.speech.whisper import FasterWhisperTranscriber
from assistant.core.storage import Storage, open_storage


class AssistantService(
    ThreadsMixin,
    ArchiveMixin,
    MemoryMixin,
    TelegramMixin,
    EmailMixin,
    IdentityMixin,
    SkillsMixin,
    JobsMixin,
    UsageMixin,
    MessagingMixin,
    RunsMixin,
    LockingMixin,
):
    def __init__(self, storage: Storage, model: str, bus: EventBus):
        self._storage = storage
        self.bus = bus
        self.outbox = Outbox()
        self._digester = build_digester(settings.worker_model)
        self._graph = build_graph(storage, model, self._digester)
        self._background = set()
        self._transcriber = FasterWhisperTranscriber()
        self._thread_locks = defaultdict(asyncio.Lock)

    @property
    def store(self):
        """The long-term Store, for daemon components (the scheduler) that manage their own records."""
        return self._storage.store

    @classmethod
    @asynccontextmanager
    async def open(cls, model: str | None = None) -> AsyncIterator["AssistantService"]:
        observability.init_tracing()
        try:
            bus = EventBus()
            async with open_storage(settings.database_path, bus) as storage:
                yield cls(storage, model or settings.model, bus)
        finally:
            observability.flush()
