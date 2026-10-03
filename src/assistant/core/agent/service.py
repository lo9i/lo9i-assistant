import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from assistant.core import observability
from assistant.core.agent.alerts import AlertsMixin
from assistant.core.agent.archive import ArchiveMixin
from assistant.core.agent.devices import DevicesMixin
from assistant.core.agent.email import EmailMixin
from assistant.core.agent.identity import IdentityMixin
from assistant.core.agent.jobs import JobsMixin
from assistant.core.agent.locking import LockingMixin
from assistant.core.agent.mcp import McpMixin
from assistant.core.agent.memory import MemoryMixin
from assistant.core.agent.messaging import MessagingMixin
from assistant.core.agent.model import ModelMixin, usable_choice
from assistant.core.agent.repositories import RepositoriesMixin
from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.skills import SkillsMixin
from assistant.core.agent.slack import SlackMixin
from assistant.core.agent.speech import SpeechMixin
from assistant.core.agent.telegram import TelegramMixin
from assistant.core.agent.threads import ThreadsMixin
from assistant.core.agent.usage import UsageMixin
from assistant.core.approvals import RemoteApprovals
from assistant.core.bus import EventBus
from assistant.core.config import settings
from assistant.core.health import HealthLog
from assistant.core.integrations.email import accounts
from assistant.core.llm import choice
from assistant.core.llm.choice import ModelChoice
from assistant.core.mcp.hub import McpHub
from assistant.core.mcp.pages import McpPages
from assistant.core.memory import profile
from assistant.core.outbox import Outbox
from assistant.core.secret_store import SecretBox
from assistant.core.speech.kokoro import KokoroSynthesizer
from assistant.core.speech.whisper import FasterWhisperTranscriber
from assistant.core.storage import Storage, open_storage


class AssistantService(
    ThreadsMixin,
    ArchiveMixin,
    MemoryMixin,
    TelegramMixin,
    SlackMixin,
    EmailMixin,
    McpMixin,
    AlertsMixin,
    RepositoriesMixin,
    ModelMixin,
    DevicesMixin,
    IdentityMixin,
    SpeechMixin,
    SkillsMixin,
    JobsMixin,
    UsageMixin,
    MessagingMixin,
    RunsMixin,
    LockingMixin,
):
    def __init__(self, storage: Storage, model: ModelChoice, bus: EventBus, secrets: SecretBox):
        self._storage = storage
        self.secrets = secrets
        self.bus = bus
        self.outbox = Outbox()
        self.approvals = RemoteApprovals()
        self._health = HealthLog(storage.store, bus)
        self.mcp = McpHub(storage.store, bus, self._health)
        self.pages = McpPages(storage.store)
        self._use_model(model)
        self._background = set()
        self._conversations_lock = asyncio.Lock()
        self._transcriber = FasterWhisperTranscriber()
        self._synthesizer = KokoroSynthesizer()
        self._thread_locks = defaultdict(asyncio.Lock)
        self._active_runs = {}

    @property
    def store(self):
        """The long-term Store, for daemon components (the scheduler) that manage their own records."""
        return self._storage.store

    @classmethod
    @asynccontextmanager
    async def open(cls) -> AsyncIterator["AssistantService"]:
        observability.init_tracing()
        try:
            bus = EventBus()
            secrets = await asyncio.to_thread(SecretBox.open, Path(settings.secrets_key_path).expanduser())
            async with open_storage(settings.database_path, bus) as storage:
                await accounts.migrate(storage.store, secrets)
                await choice.migrate(storage.store, secrets)
                await profile.migrate(storage.store)
                yield cls(storage, await usable_choice(storage.store, secrets), bus, secrets)
        finally:
            observability.flush()
