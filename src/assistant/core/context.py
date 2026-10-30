from abc import ABC, abstractmethod
from collections.abc import Collection
from dataclasses import dataclass, field

from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from assistant.core.bus import EventBus
from assistant.core.conversation.meanings import SimilarConversations
from assistant.core.conversation.search import MessageIndex
from assistant.core.memory.recall import MemoryRecall
from assistant.core.outbox import Outbox
from assistant.core.secret_store import SecretBox
from assistant.core.subagent_steps import SubagentAnswer

# The channel scheduled jobs run on.
UNATTENDED_CHANNEL = "worker"


class Subagents(ABC):
    """Runs a task in a subagent of its own and returns its answer, with the steps it took
    (core/subagent.py). A base class, not a Protocol: tools validate the context with pydantic, which can't
    check a Protocol."""

    @abstractmethod
    async def run(
        self, task: str, context: "Context", call_id: str, plugins: Collection[str], agent: str = ""
    ) -> SubagentAnswer:
        """`call_id`: the delegate call's, which the subagent's tool events name. `plugins`: those the
        conversation loaded (core/plugin_loading.py), whose read-only tools the subagent gets. `agent`: a named
        subagent a plugin brings (core/mcp/subagents.py), "" for the general one; an unknown one raises
        UnknownSubagentError."""


class McpStarts(ABC):
    """Waits for an MCP server that's starting (core/mcp/hub.py). A base class for the same reason as
    Subagents."""

    @abstractmethod
    async def started(self, name: str, timeout: float) -> str:
        """Waits up to `timeout` seconds while the server is connecting or retrying, and returns its status
        then: connected, connecting, failed, needs_sign_in, idle (on demand and stopped),
        or off when it isn't running."""


@dataclass
class Context:
    """Per-run values passed to graph nodes and tools. Not stored in checkpoints."""

    user_id: str
    channel: str
    # For tools whose changes the store doesn't see (skills are files).
    bus: EventBus | None = field(default=None, compare=False)
    # For messages the agent starts itself (send_message).
    outbox: Outbox | None = field(default=None, compare=False)
    # For tools that use an account's password or token.
    secrets: SecretBox | None = field(default=None, compare=False)
    # For searching past conversations.
    search: MessageIndex | None = field(default=None, compare=False)
    # For searching saved facts and episodes by meaning.
    recall: MemoryRecall | None = field(default=None, compare=False)
    # For routing from the inbox: the conversations closest in meaning to a message.
    similar: SimilarConversations | None = field(default=None, compare=False)
    # For delegate. None inside a subagent, so subagents don't start their own.
    subagents: Subagents | None = field(default=None, compare=False)
    # For offer_plugin, which waits for the server the user just installed.
    mcp: McpStarts | None = field(default=None, compare=False)
    # An unattended run whose approvals are sent to the user (core/approvals.py) instead of denied.
    forwards_approvals: bool = False

    @property
    def unattended(self) -> bool:
        """Scheduled runs: nobody is watching them."""
        return self.channel == UNATTENDED_CHANNEL


def require_secrets(context: Context) -> SecretBox:
    """The service always passes its secrets to runs (`core/agent/runs.py`)."""
    if context.secrets is None:
        raise RuntimeError("The run was started without the secrets.")
    return context.secrets


def require_search(context: Context) -> MessageIndex:
    """The service always passes its search index to runs (`core/agent/runs.py`)."""
    if context.search is None:
        raise RuntimeError("The run was started without the search index.")
    return context.search


def require_recall(context: Context) -> MemoryRecall:
    """The service always passes its memory search to runs (`core/agent/runs.py`)."""
    if context.recall is None:
        raise RuntimeError("The run was started without the memory search.")
    return context.recall


def thread_of(config: RunnableConfig) -> str:
    """The id of the conversation a run is in."""
    return (config.get("configurable") or {}).get("thread_id", "")


def require_store(store: BaseStore | None) -> BaseStore:
    """The graph's store. The graph is always compiled with one (`core/graph.py`)."""
    if store is None:
        raise RuntimeError("The graph was compiled without a store.")
    return store
