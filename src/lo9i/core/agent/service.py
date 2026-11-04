import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from lo9i.core import observability
from lo9i.core.agent.about_you import AboutYouMixin
from lo9i.core.agent.alerts import AlertsMixin
from lo9i.core.agent.archive import ArchiveMixin
from lo9i.core.agent.channel_threads import ChannelThreadsMixin
from lo9i.core.agent.channels import ChannelsMixin
from lo9i.core.agent.devices import DevicesMixin
from lo9i.core.agent.dispatch import DispatchMixin
from lo9i.core.agent.doctor import DoctorMixin
from lo9i.core.agent.email import EmailMixin
from lo9i.core.agent.files import FilesMixin
from lo9i.core.agent.follow_ups import FollowUpsMixin
from lo9i.core.agent.handed_folder import HandedFolderMixin
from lo9i.core.agent.held import HeldRunsMixin
from lo9i.core.agent.home import HomeMixin
from lo9i.core.agent.identity import IdentityMixin
from lo9i.core.agent.jobs import JobsMixin
from lo9i.core.agent.language import LanguageMixin
from lo9i.core.agent.locking import LockingMixin
from lo9i.core.agent.log_level import LogLevelMixin
from lo9i.core.agent.mcp import McpMixin
from lo9i.core.agent.memory import MemoryMixin
from lo9i.core.agent.messaging import MessagingMixin
from lo9i.core.agent.model import ModelMixin, usable_choice
from lo9i.core.agent.notifications import NotificationsMixin
from lo9i.core.agent.own_model import OwnModelMixin
from lo9i.core.agent.passkeys import PasskeysMixin
from lo9i.core.agent.pinned import PinnedSkillsMixin
from lo9i.core.agent.plugin_settings import PluginSettingsMixin
from lo9i.core.agent.proactive import ProactiveMixin
from lo9i.core.agent.prompts import PromptsMixin
from lo9i.core.agent.repositories import RepositoriesMixin
from lo9i.core.agent.runs import RunsMixin
from lo9i.core.agent.sign_ins import SignInsMixin
from lo9i.core.agent.skill_imports import SkillImportsMixin
from lo9i.core.agent.skills import SkillsMixin
from lo9i.core.agent.speech import SpeechMixin
from lo9i.core.agent.subagents import SubagentsMixin
from lo9i.core.agent.tasks import TasksMixin
from lo9i.core.agent.threads import ThreadsMixin
from lo9i.core.agent.usage import UsageMixin
from lo9i.core.agent.voice_calls import VoiceCallsMixin
from lo9i.core.agent.web_search import WebSearchMixin
from lo9i.core.agent_tasks.ends import TaskEnds
from lo9i.core.agent_tasks.reports import TaskReports
from lo9i.core.agent_tasks.service import AgentTasks
from lo9i.core.agent_tasks.tools import AgentTools
from lo9i.core.approvals import RemoteApprovals
from lo9i.core.background import BackgroundEnds
from lo9i.core.background_subagents.runner import BackgroundSubagents
from lo9i.core.bus import EventBus
from lo9i.core.channels.hub import ChannelHub
from lo9i.core.channels.processes import ChannelProcesses
from lo9i.core.config import settings
from lo9i.core.conversation import prompt_edits
from lo9i.core.conversation.meanings import ConversationIndexer, SimilarConversations
from lo9i.core.conversation.memory_writer import MemoryWriter
from lo9i.core.conversation.past_outputs import PastOutputs
from lo9i.core.copilot_quota.section import CopilotSection
from lo9i.core.copilot_quota.watch import CopilotWatch
from lo9i.core.doctor.doctor import Doctor
from lo9i.core.doctor.schedule import DoctorSchedule
from lo9i.core.ending import EndingState
from lo9i.core.health import HealthLog
from lo9i.core.home import sections as home_sections
from lo9i.core.home.conversations import ConversationsSection
from lo9i.core.home.loops import LoopsSection
from lo9i.core.home.refresh import HomeRefresh
from lo9i.core.home.schedule import HomeSchedule
from lo9i.core.llm import choice
from lo9i.core.llm.choice import ModelChoice
from lo9i.core.llm.windows import ContextWindows
from lo9i.core.mcp import folders, logins
from lo9i.core.mcp import install as plugin_install
from lo9i.core.mcp import keys as plugin_keys
from lo9i.core.mcp.badges import Badges
from lo9i.core.mcp.checks import PluginChecks
from lo9i.core.mcp.environment import Environments
from lo9i.core.mcp.hub import McpHub
from lo9i.core.mcp.media import ToolMedia
from lo9i.core.mcp.oauth import McpAuth
from lo9i.core.mcp.pages import McpPages
from lo9i.core.mcp.sampling import Sampler
from lo9i.core.mcp.today import TodayLists
from lo9i.core.memory import profile
from lo9i.core.memory.e5 import E5Embedder
from lo9i.core.memory.indexer import MemoryIndexer
from lo9i.core.memory.recall import MemoryRecall
from lo9i.core.oauth import SignIns
from lo9i.core.outbox import Outbox
from lo9i.core.passkeys import Ceremonies
from lo9i.core.plugin_tools import PluginTools
from lo9i.core.proactive.briefing import Briefer
from lo9i.core.proactive.mail import UnreadMail
from lo9i.core.proactive.reminders import Reminders
from lo9i.core.proactive.review import Reviewer
from lo9i.core.proactive.schedule import ProactiveRuns, ProactiveSchedule
from lo9i.core.proactive.telling import Teller
from lo9i.core.repositories.checker import UpdateChecker
from lo9i.core.secret_store import SecretBox
from lo9i.core.speech.heard import HeardOnce
from lo9i.core.speech.kokoro import KokoroSynthesizer
from lo9i.core.speech.whisper import FasterWhisperTranscriber
from lo9i.core.storage import Storage, open_storage
from lo9i.core.tools.registry import tool_groups
from lo9i.core.usage.alerts import SpendingAlerts
from lo9i.core.usage.budget import Budget
from lo9i.core.voice.realtime import OpenAIRealtime
from lo9i.core.voice.tool_calls import ToolCalls


class AssistantService(
    ChannelThreadsMixin,
    ThreadsMixin,
    ArchiveMixin,
    FilesMixin,
    HandedFolderMixin,
    MemoryMixin,
    AboutYouMixin,
    SignInsMixin,
    EmailMixin,
    ChannelsMixin,
    PluginSettingsMixin,
    McpMixin,
    AlertsMixin,
    DoctorMixin,
    NotificationsMixin,
    HomeMixin,
    ProactiveMixin,
    FollowUpsMixin,
    HeldRunsMixin,
    TasksMixin,
    SubagentsMixin,
    RepositoriesMixin,
    ModelMixin,
    DevicesMixin,
    PasskeysMixin,
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
    OwnModelMixin,
    JobsMixin,
    UsageMixin,
    VoiceCallsMixin,
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
        self._transcriber = HeardOnce(FasterWhisperTranscriber())
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
            sampler=Sampler(lambda: self._model, storage.usage),
        )
        self.agent_tasks = AgentTasks(storage.store, secrets, environments, lambda: logins.of_model(self._model))
        self._plugin_checks = PluginChecks(storage.store, secrets, lambda: logins.of_model(self._model), environments)
        self._task_reports = TaskReports(storage.store)
        self.task_ends = TaskEnds(self.agent_tasks, self._task_reports, bus, background)
        self.ending = EndingState(Path(settings.restart_pending_path).expanduser(), lambda: sorted(self._active_runs))
        self._plugin_tools = PluginTools(
            self.mcp,
            AgentTools(self.agent_tasks, self._task_reports, self.ending, storage.store),
            tool_groups(settings.toolsets),
        )
        coded = {
            home_sections.COPILOT: CopilotSection(storage.store, lambda: self._model),
            home_sections.CONVERSATIONS: ConversationsSection(
                storage.store, settings.owner_id, lambda: self.list_conversations(settings.owner_id)
            ),
            home_sections.LOOPS: LoopsSection(storage.store, settings.owner_id),
        }
        self.today_lists = TodayLists(storage.store, self.mcp)
        self.badges = Badges(storage.store, self.mcp)
        self.home_refresh = HomeRefresh(
            storage.store, bus, lambda: self._home_builder, self._plugin_tools, coded, self.today_lists
        )
        self.home_schedule = HomeSchedule(storage.store, self.home_refresh, settings.owner_id, bus)
        self.copilot_watch = CopilotWatch(
            storage.store,
            self.outbox,
            lambda: self._model,
            lambda: self.home_refresh.refresh(settings.owner_id, only=[home_sections.COPILOT]),
            settings.owner_id,
        )
        self._windows = ContextWindows(storage.store)
        self._passkey_ceremonies = Ceremonies()
        self._budget = Budget(
            storage.usage, storage.store, SpendingAlerts(storage.store, self.outbox, settings.owner_id)
        )
        storage.usage.guard = self._budget
        self.doctor = Doctor(
            storage.store,
            bus,
            lambda: self._graph,
            lambda: self._active_runs.keys(),
            self._plugin_tools,
            lambda: self._windows.of(self._model),
        )
        self.doctor_schedule = DoctorSchedule(storage.store, self.doctor, settings.owner_id)
        teller, unread = Teller(storage.store, self.outbox, settings.owner_id), UnreadMail(storage.store, secrets)
        self.proactive_runs = ProactiveRuns(
            bus,
            Briefer(storage.store, lambda: self._proactive_models, self.today_lists, unread, teller, settings.owner_id),
            Reviewer(
                storage.store,
                storage.checkpointer,
                lambda: self._proactive_models,
                self.today_lists,
                unread,
                settings.owner_id,
            ),
        )
        self.proactive_schedule = ProactiveSchedule(
            storage.store, self.proactive_runs, Reminders(storage.store, teller, settings.owner_id), settings.owner_id
        )
        self.pages = McpPages(storage.store, environments, secrets)
        self.channels_hub = ChannelHub(
            self.outbox, self.approvals, bus, self.assistant_name, self.channel_commands, self.texts
        )
        self.channel_processes = ChannelProcesses(storage.store, self.channels_hub, environments, secrets)
        embedder = E5Embedder()
        self.memory_index = MemoryIndexer(storage.store, storage.vectors, embedder, bus)
        self._recall = MemoryRecall(storage.store, storage.vectors, embedder)
        self._past_outputs = PastOutputs(storage.checkpointer, storage.search)
        self.conversation_index = ConversationIndexer(storage.store, storage.search, storage.vectors, embedder, bus)
        self._similar = SimilarConversations(storage.vectors, embedder)
        self.memory_writer = MemoryWriter(
            storage.store, storage.checkpointer, bus, lambda: self._digester, self._recall
        )
        self.update_checker = UpdateChecker(storage.store, bus, secrets)
        self._sign_ins = SignIns()
        self.background_subagents = BackgroundSubagents(
            storage, bus, self._health, self.approvals, background, lambda: self._subagents, self._run_context
        )
        self._use_model(model)
        self._background = set()
        self._untitled = set()
        self._titling = asyncio.Lock()
        self._conversations_lock = asyncio.Lock()
        self._synthesizer = KokoroSynthesizer()
        self.realtime = OpenAIRealtime()
        self.voice_tool_calls = ToolCalls(storage.store)
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
