import asyncio

from lo9i.core.agent_tasks.ends import TaskEnds
from lo9i.core.agent_tasks.reports import TaskReports
from lo9i.core.agent_tasks.service import AgentTasks
from lo9i.core.approvals import RemoteApprovals
from lo9i.core.background_subagents.runner import BackgroundSubagents
from lo9i.core.bus import EventBus
from lo9i.core.channels.hub import ChannelHub
from lo9i.core.channels.processes import ChannelProcesses
from lo9i.core.conversation.digest import Digester
from lo9i.core.conversation.dispatch import Classifier
from lo9i.core.conversation.meanings import ConversationIndexer, SimilarConversations
from lo9i.core.conversation.memory_writer import MemoryWriter
from lo9i.core.conversation.past_outputs import PastOutputs
from lo9i.core.conversation.titles import Titler
from lo9i.core.copilot_quota.watch import CopilotWatch
from lo9i.core.doctor.doctor import Doctor
from lo9i.core.doctor.schedule import DoctorSchedule
from lo9i.core.ending import EndingState
from lo9i.core.graph import Graph
from lo9i.core.health import HealthLog
from lo9i.core.home.builder import SectionBuilder
from lo9i.core.home.refresh import HomeRefresh
from lo9i.core.home.schedule import HomeSchedule
from lo9i.core.llm.choice import ModelChoice
from lo9i.core.llm.windows import ContextWindows
from lo9i.core.mcp.checks import PluginChecks
from lo9i.core.mcp.hub import McpHub
from lo9i.core.mcp.pages import McpPages
from lo9i.core.mcp.today import TodayLists
from lo9i.core.memory.indexer import MemoryIndexer
from lo9i.core.memory.recall import MemoryRecall
from lo9i.core.oauth import SignIns
from lo9i.core.outbox import Outbox
from lo9i.core.passkeys import Ceremonies
from lo9i.core.plugin_tools import PluginTools
from lo9i.core.proactive.schedule import ProactiveRuns, ProactiveSchedule
from lo9i.core.proactive.writing import ProactiveModels
from lo9i.core.repositories.checker import UpdateChecker
from lo9i.core.secret_store import SecretBox
from lo9i.core.speech.synthesizer import Synthesizer
from lo9i.core.speech.transcriber import Transcriber
from lo9i.core.storage import Storage
from lo9i.core.subagent import SubagentRunner
from lo9i.core.usage.budget import Budget
from lo9i.core.voice.realtime import Realtime
from lo9i.core.voice.tool_calls import ToolCalls


class ServiceBase:
    """State shared by the service mixins. Set by `AssistantService.__init__`."""

    _storage: Storage
    bus: EventBus
    # Connected channels register here to deliver messages the agent starts (core/outbox.py).
    outbox: Outbox
    # Connected channels that can show approvals for scheduled runs register here (core/approvals.py).
    approvals: RemoteApprovals
    # The channel plugins' processes while they're connected (core/channels/hub.py).
    channels_hub: ChannelHub
    # Runs those processes. The daemon runs it as a supervised task.
    channel_processes: ChannelProcesses
    # MCP server connections. The daemon runs it as a supervised task.
    mcp: McpHub
    # Plugins' checks of the values they're given, run before those are saved (core/mcp/checks.py).
    _plugin_checks: PluginChecks
    # The coding agents plugins bring and their tasks (core/agent_tasks/).
    agent_tasks: AgentTasks
    # The conversation that started each task whose end is still to be told.
    _task_reports: TaskReports
    # Tells a conversation that a task it started ended. The daemon runs it as a supervised task.
    task_ends: TaskEnds
    # The restart or stop of the daemon waiting for runs (core/ending.py), which the daemon's shutdown keeps.
    ending: EndingState
    # The tools plugins bring, MCP servers' and the agents' task tools, for the graph and subagents.
    _plugin_tools: PluginTools
    # The web pages MCP servers come with, run like `mcp`.
    pages: McpPages
    # Embeds new facts and episodes for memory search. The daemon runs it as a supervised task.
    memory_index: MemoryIndexer
    conversation_index: ConversationIndexer
    # Digests archived parts of conversations into memory. The daemon runs it as a supervised task.
    memory_writer: MemoryWriter
    _recall: MemoryRecall
    # Passkey registrations and sign-ins waiting for the browser's answer (core/passkeys.py).
    _passkey_ceremonies: Ceremonies
    _past_outputs: PastOutputs
    _similar: SimilarConversations
    # Checks the extras for newer plugin versions. The daemon runs it as a supervised task.
    update_checker: UpdateChecker
    # Encrypts accounts' passwords and tokens (core/secret_store.py).
    secrets: SecretBox
    # Sign-ins (OAuth: email accounts, MCP servers) waiting for the browser to come back.
    _sign_ins: SignIns
    # Failures of MCP servers and skills in a row (core/health.py), shared with `mcp`.
    _health: HealthLog
    _graph: Graph
    # Runs delegated tasks; rebuilt with the graph when the model changes.
    _subagents: SubagentRunner
    # Subagents sent off in the background (core/background_subagents/). The daemon runs it as a supervised task.
    background_subagents: BackgroundSubagents
    # Picks where a message goes (core/conversation/dispatch.py) outside the graph; rebuilt with it.
    _classify: Classifier
    # The plugins' lists for the day (core/mcp/today.py): Home, the briefing and the nightly review read them.
    today_lists: TodayLists
    # Builds Home's sections in the background (core/home/), with the builder of the model in use. Requests start
    # its refreshes; the daemon doesn't run it as a task.
    home_refresh: HomeRefresh
    # Refreshes Home at the start of the day and while a client shows it. The daemon runs it as a supervised task.
    home_schedule: HomeSchedule
    # Checks the Copilot plan's allowance without the model, for Home and alerts. The daemon runs it as a supervised
    # task.
    copilot_watch: CopilotWatch
    # Checks the daemon's health (core/doctor/); requests start a check of today in the background.
    doctor: Doctor
    # Checks each day once it ended. The daemon runs it as a supervised task.
    doctor_schedule: DoctorSchedule
    _home_builder: SectionBuilder
    # The briefing and reviews running now (core/proactive/); requests start them too.
    proactive_runs: ProactiveRuns
    # Runs them at the user's times and sends reminders. The daemon runs it as a supervised task.
    proactive_schedule: ProactiveSchedule
    # The worker model's gathering and writers they use, rebuilt with the model.
    _proactive_models: ProactiveModels
    # OpenAI's Realtime API, for live voice calls (core/voice/); the tests fake it.
    realtime: Realtime
    # The voice model's tool calls by their id, so one made again gets the first result (core/voice/tool_calls.py).
    voice_tool_calls: ToolCalls
    _transcriber: Transcriber
    _synthesizer: Synthesizer
    _digester: Digester
    _titler: Titler
    # Background work (archiving) kept referenced until it finishes.
    _background: set[asyncio.Task]
    # Conversations (user id, thread id) whose titling failed, titled again once the worker model answers
    # (core/agent/titles.py), and held while a pass titles them.
    _untitled: set[tuple[str, str]]
    _titling: asyncio.Lock
    # Conversation records are read, changed and saved by turns, titling and archiving, which
    # run concurrently; each change holds this, so none saves over another's.
    _conversations_lock: asyncio.Lock
    # The task running each thread's graph, while it runs (core/agent/runs.py).
    _active_runs: dict[str, asyncio.Task]
    # How many messages each thread had when its run in progress started (core/agent/runs.py).
    _run_starts: dict[str, int]
    # How many runs are in progress, each counted until its cleanup is done, and set while none is
    # (core/agent/runs.py).
    _open_runs: int
    _no_runs: asyncio.Event
    # While set, new runs are kept to run later instead: an update installs (`hold_runs`, core/agent/runs.py).
    _held: bool
    # The model in use (core/agent/model.py), and each model's context window, what a conversation's context is
    # measured against (core/llm/windows.py).
    _model: ModelChoice
    _windows: ContextWindows
    # Holds every model call to the spending limits (core/usage/budget.py), as the token ledger's guard.
    _budget: Budget

    async def _servers_changed(self) -> None:
        """Bring MCP connections, coding agents, pages and channels in line with the saved servers. A server's skill
        comes and goes with it, so clients refresh their skills too."""
        await self.mcp.reload()
        await self.agent_tasks.reload()
        await self.pages.reload()
        await self.channel_processes.reload()
        self.bus.publish("skills")
        self.bus.publish("channels")
