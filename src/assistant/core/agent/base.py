import asyncio

from assistant.core.agent_tasks.service import AgentTasks
from assistant.core.approvals import RemoteApprovals
from assistant.core.bus import EventBus
from assistant.core.channels.hub import ChannelHub
from assistant.core.channels.processes import ChannelProcesses
from assistant.core.conversation.digest import Digester
from assistant.core.conversation.memory_writer import MemoryWriter
from assistant.core.conversation.titles import Titler
from assistant.core.graph import Graph
from assistant.core.health import HealthLog
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
    # The tools plugins bring, MCP servers' and the agents' task tools, for the graph and subagents.
    _plugin_tools: PluginTools
    # The web pages MCP servers come with, run like `mcp`.
    pages: McpPages
    # Embeds new facts and episodes for memory search. The daemon runs it as a supervised task.
    memory_index: MemoryIndexer
    # Digests archived parts of conversations into memory. The daemon runs it as a supervised task.
    memory_writer: MemoryWriter
    _recall: MemoryRecall
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
    _transcriber: Transcriber
    _synthesizer: Synthesizer
    _digester: Digester
    _titler: Titler
    # Background work (archiving) kept referenced until it finishes.
    _background: set[asyncio.Task]
    # Conversation records are read, changed and saved by turns, titling and archiving, which
    # run concurrently; each change holds this, so none saves over another's.
    _conversations_lock: asyncio.Lock
    # The task running each thread's graph, while it runs (core/agent/runs.py).
    _active_runs: dict[str, asyncio.Task]
    # Set while no run is in progress (core/agent/runs.py).
    _no_runs: asyncio.Event

    async def _servers_changed(self) -> None:
        """Bring MCP connections, coding agents, pages and channels in line with the saved servers. A server's skill
        comes and goes with it, so clients refresh their skills too."""
        await self.mcp.reload()
        await self.agent_tasks.reload()
        await self.pages.reload()
        await self.channel_processes.reload()
        self.bus.publish("skills")
        self.bus.publish("channels")
