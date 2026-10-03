from dataclasses import dataclass, field

from langgraph.store.base import BaseStore

from assistant.core.bus import EventBus
from assistant.core.conversation.search import MessageIndex
from assistant.core.memory.recall import MemoryRecall
from assistant.core.outbox import Outbox
from assistant.core.secret_store import SecretBox

# The channel scheduled jobs run on.
UNATTENDED_CHANNEL = "worker"


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


def require_store(store: BaseStore | None) -> BaseStore:
    """The graph's store. The graph is always compiled with one (`core/graph.py`)."""
    if store is None:
        raise RuntimeError("The graph was compiled without a store.")
    return store
