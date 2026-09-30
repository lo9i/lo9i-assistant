from dataclasses import dataclass, field

from langgraph.store.base import BaseStore

from assistant.core.bus import EventBus
from assistant.core.outbox import Outbox

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

    @property
    def unattended(self) -> bool:
        """Scheduled runs: nobody is there to approve anything."""
        return self.channel == UNATTENDED_CHANNEL


def require_store(store: BaseStore | None) -> BaseStore:
    """The graph's store. The graph is always compiled with one (`core/graph.py`)."""
    if store is None:
        raise RuntimeError("The graph was compiled without a store.")
    return store
