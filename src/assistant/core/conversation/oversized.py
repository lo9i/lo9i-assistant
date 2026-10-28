"""A model call refused as too large (core/llm/errors.py) is recovered once: the conversation is compacted to its
last user turn, the older part summarized as when an epoch fills up (epochs.py), and every tool result and file
left in the epoch is sent as a stub (trim.py), the current turn's too, since what made it too large may be there
(a screenshot the user just sent, a browser's screenshots). The call is then made again. Refused again with
nothing new since, the run fails with a plain message.

The checkpoint keeps every message whole, as always."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from langgraph.store.base import BaseStore

from assistant.core.conversation.epochs import compact
from assistant.core.conversation.summary import Summarizer


class ConversationTooLargeError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "The model refused the request as too large, even with this conversation compacted and its files left "
            "out. Send a shorter message, or start a new conversation with /new."
        )


async def shrink(
    state: Mapping[str, Any],
    store: BaseStore,
    user_id: str,
    thread_id: str,
    summarizer: Summarizer,
    now: datetime,
    plugin_tools: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """State update that makes the next model call as small as the conversation allows."""
    update = await compact(state, store, user_id, thread_id, summarizer, now, plugin_tools, keep_turns=1)
    return {**update, "trimmed_before": len(state["messages"]), "usage_anchor": None}


def shrunk_already(state: Mapping[str, Any]) -> bool:
    """The conversation was shrunk with nothing added since, so shrinking it again would change nothing."""
    return state.get("shrunk_at") == len(state["messages"])
