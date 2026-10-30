import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from assistant.core import observability
from assistant.core.agent.alerts import AlertsMixin
from assistant.core.agent.archive import ArchiveMixin
from assistant.core.agent.channel_threads import ChannelThreadsMixin
from assistant.core.agent.channels import ChannelsMixin
from assistant.core.agent.devices import DevicesMixin
from assistant.core.agent.dispatch import DispatchMixin
from assistant.core.agent.doctor import DoctorMixin
from assistant.core.agent.email import EmailMixin
from assistant.core.agent.files import FilesMixin
from assistant.core.agent.follow_ups import FollowUpsMixin
from assistant.core.agent.handed_folder import HandedFolderMixin
from assistant.core.agent.held import HeldRunsMixin
from assistant.core.agent.home import HomeMixin
from assistant.core.agent.identity import IdentityMixin
from assistant.core.agent.jobs import JobsMixin
from assistant.core.agent.language import LanguageMixin
from assistant.core.agent.locking import LockingMixin
from assistant.core.agent.log_level import LogLevelMixin
from assistant.core.agent.mcp import McpMixin
from assistant.core.agent.memory import MemoryMixin
from assistant.core.agent.messaging import MessagingMixin
from assistant.core.agent.model import ModelMixin, usable_choice
from assistant.core.agent.notifications import NotificationsMixin
from assistant.core.agent.pinned import PinnedSkillsMixin
from assistant.core.agent.prompts import PromptsMixin
from assistant.core.agent.repositories import RepositoriesMixin
from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.sign_ins import SignInsMixin
from assistant.core.agent.skill_imports import SkillImportsMixin
from assistant.core.agent.skills import SkillsMixin
from assistant.core.agent.speech import SpeechMixin
from assistant.core.agent.tasks import TasksMixin
from assistant.core.agent.threads import ThreadsMixin
from assistant.core.agent.usage import UsageMixin
from assistant.core.agent.web_search import WebSearchMixin
from assistant.core.agent_tasks.ends import TaskEnds
from assistant.core.agent_tasks.reports import TaskReports
from assistant.core.agent_tasks.service import AgentTasks
from assistant.core.agent_tasks.tools import AgentTools
from assistant.core.approvals import RemoteApprovals
from assistant.core.background import BackgroundEnds
from assistant.core.bus import EventBus
from assistant.core.channels.hub import ChannelHub
from assistant.core.channels.processes import ChannelProcesses
from assistant.core.config import settings
from assistant.core.conversation import prompt_edits
from assistant.core.conversation.meanings import ConversationIndexer, SimilarConversations
from assistant.core.conversation.memory_writer import MemoryWriter
from assistant.core.copilot_quota.section import CopilotSection
from assistant.core.copilot_quota.watch import CopilotWatch
from assistant.core.doctor.doctor import Doctor
from assistant.core.doctor.schedule import DoctorSchedule
from assistant.core.health import HealthLog
from assistant.core.home import sections as home_sections
from assistant.core.home.refresh import HomeRefresh
from assistant.core.home.schedule import HomeSchedule
from assistant.core.llm import choice
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.windows import ContextWindows
from assistant.core.mcp import folders, logins
from assistant.core.mcp import install as plugin_install
from assistant.core.mcp import keys as plugin_keys
from assistant.core.mcp.environment import Environments
from assistant.core.mcp.hub import McpHub
from assistant.core.mcp.media import ToolMedia
from assistant.core.mcp.oauth import McpAuth
from assistant.core.mcp.pages import McpPages
from assistant.core.memory import profile
from assistant.core.memory.e5 import E5Embedder
from assistant.core.memory.indexer import MemoryIndexer
from assistant.core.memory.recall import MemoryRecall
from assistant.core.oauth import SignIns
from assistant.core.outbox import Outbox
from assistant.core.plugin_tools import PluginTools
from assistant.core.repositories.checker import UpdateChecker
from assistant.core.secret_store import SecretBox
from assistant.core.speech.kokoro import KokoroSynthesizer
from assistant.core.speech.whisper import FasterWhisperTranscriber
from assistant.core.storage import Storage, open_storage
from assistant.core.tools.registry import tool_groups


class AssistantService(
    ChannelThreadsMixin,
    ThreadsMixin,
    ArchiveMixin,
    FilesMixin,
    HandedFolderMixin,
    MemoryMixin,
    SignInsMixin,
    EmailMixin,
    ChannelsMixin,
    McpMixin,
    AlertsMixin,
    DoctorMixin,
    NotificationsMixin,
    HomeMixin,
    FollowUpsMixin,
    HeldRunsMixin,
    TasksMixin,
    RepositoriesMixin,
    ModelMixin,
    DevicesMixin,
    IdentityMixin,
    PromptsMixin,
    SpeechMixin,
    LogLevelMixin,
    LanguageMixin,
    DispatchMixin,
    WebSearchMixin,
    SkillsMixin,
    SkillImportsMixin,
    PinnedSkillsMixin,
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
        self._transcriber = FasterWhisperTranscriber()
        media = ToolMedia(self._transcriber, storage.store)
        auth = McpAuth(storage.store, secrets)
        environments = Environments(folders.code)
        background = BackgroundEnds(storage.store, self.outbox, bus)
        self.mcp = McpHub(
            storage.store,
            bus,
            self._health,
            media,
            auth,
            secrets,
            shared=lambda: logins.of_model(self._model),
            environments=environments,
            background=background,
        )
        self.agent_tasks = AgentTasks(storage.store, secrets, environments, lambda: logins.of_model(self._model))
        self._task_reports = TaskReports(storage.store)
        self.task_ends = TaskEnds(self.agent_tasks, self._task_reports, bus, background)
        self._plugin_tools = PluginTools(
            self.mcp, AgentTools(self.agent_tasks, self._task_reports), tool_groups(settings.toolsets)
        )
        coded = {home_sections.COPILOT: CopilotSection(storage.store, lambda: self._model)}
        self.home_refresh = HomeRefresh(storage.store, bus, lambda: self._home_builder, self._plugin_tools, coded)
        self.home_schedule = HomeSchedule(storage.store, self.home_refresh, settings.owner_id)
        self.copilot_watch = CopilotWatch(
            storage.store,
            self.outbox,
            lambda: self._model,
            lambda: self.home_refresh.refresh(settings.owner_id, only=[home_sections.COPILOT]),
            settings.owner_id,
        )
        self._windows = ContextWindows(storage.store)
        self.doctor = Doctor(
            storage.store,
            bus,
            lambda: self._graph,
            lambda: self._active_runs.keys(),
            self._plugin_tools,
            lambda: self._windows.of(self._model),
        )
        self.doctor_schedule = DoctorSchedule(storage.store, self.doctor, settings.owner_id)
        self.pages = McpPages(storage.store, environments, secrets)
        self.channels_hub = ChannelHub(
            self.outbox, self.approvals, bus, self.assistant_name, self.channel_commands, self.texts
        )
        self.channel_processes = ChannelProcesses(storage.store, self.channels_hub, environments, secrets)
        embedder = E5Embedder()
        self.memory_index = MemoryIndexer(storage.store, storage.vectors, embedder, bus)
        self._recall = MemoryRecall(storage.store, storage.vectors, embedder)
        self.conversation_index = ConversationIndexer(storage.store, storage.search, storage.vectors, embedder, bus)
        self._similar = SimilarConversations(storage.vectors, embedder)
        self.memory_writer = MemoryWriter(
            storage.store, storage.checkpointer, bus, lambda: self._digester, self._recall
        )
        self.update_checker = UpdateChecker(storage.store, bus, secrets)
        self._sign_ins = SignIns()
        self._use_model(model)
        self._background = set()
        self._untitled = set()
        self._titling = asyncio.Lock()
        self._conversations_lock = asyncio.Lock()
        self._synthesizer = KokoroSynthesizer()
        self._thread_locks = defaultdict(asyncio.Lock)
        self._active_runs = {}
        self._run_starts = {}
        self._open_runs = 0
        self._no_runs = asyncio.Event()
        self._no_runs.set()
        self._held = False

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
                await choice.migrate(storage.store, secrets)
                await plugin_keys.migrate(storage.store, secrets)
                await plugin_install.add_missing_icons(storage.store)
                await profile.migrate(storage.store)
                await prompt_edits.keep_bases()
                await asyncio.to_thread(folders.remove_old_libraries)
                service = cls(storage, await usable_choice(storage.store, secrets), bus, secrets)
                await service.agent_tasks.reload()
                yield service
        finally:
            observability.flush()
