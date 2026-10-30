import asyncio

from assistant.core.agent_tasks.ends import TaskEnds
from assistant.core.agent_tasks.reports import TaskReports
from assistant.core.agent_tasks.service import AgentTasks
from assistant.core.approvals import RemoteApprovals
from assistant.core.bus import EventBus
from assistant.core.channels.hub import ChannelHub
from assistant.core.channels.processes import ChannelProcesses
from assistant.core.conversation.digest import Digester
from assistant.core.conversation.dispatch import Classifier
from assistant.core.conversation.meanings import ConversationIndexer, SimilarConversations
from assistant.core.conversation.memory_writer import MemoryWriter
from assistant.core.conversation.titles import Titler
from assistant.core.copilot_quota.watch import CopilotWatch
from assistant.core.doctor.doctor import Doctor
from assistant.core.doctor.schedule import DoctorSchedule
from assistant.core.graph import Graph
from assistant.core.health import HealthLog
from assistant.core.home.builder import SectionBuilder
from assistant.core.home.refresh import HomeRefresh
from assistant.core.home.schedule import HomeSchedule
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.windows import ContextWindows
from assistant.core.mcp.hub import McpHub
from assistant.core.mcp.pages import McpPages
from assistant.core.memory.indexer import MemoryIndexer
from assistant.core.memory.recall import MemoryRecall
from assistant.core.oauth import SignIns
from assistant.core.outbox import Outbox
from assistant.core.plugin_tools import PluginTools
from assistant.core.repositories.checker import UpdateChecker
from assistant.core.secret_store import SecretBox
from assistant.core.speech.synthesizer import Synthesizer
from assistant.core.speech.transcriber import Transcriber
from assistant.core.storage import Storage
from assistant.core.subagent import SubagentRunner


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
    # The coding agents plugins bring and their tasks (core/agent_tasks/).
    agent_tasks: AgentTasks
    # The conversation that started each task whose end is still to be told.
    _task_reports: TaskReports
    # Tells a conversation that a task it started ended. The daemon runs it as a supervised task.
    task_ends: TaskEnds
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
    # Picks where a message goes (core/conversation/dispatch.py) outside the graph; rebuilt with it.
    _classify: Classifier
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

    async def _servers_changed(self) -> None:
        """Bring MCP connections, coding agents, pages and channels in line with the saved servers. A server's skill
        comes and goes with it, so clients refresh their skills too."""
        await self.mcp.reload()
        await self.agent_tasks.reload()
        await self.pages.reload()
        await self.channel_processes.reload()
        self.bus.publish("skills")
        self.bus.publish("channels")
