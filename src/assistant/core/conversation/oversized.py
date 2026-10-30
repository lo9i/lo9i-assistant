"""A model call refused as too large (core/llm/errors.py) is recovered once: the conversation is compacted to its
last user turn, the older part summarized as when an epoch fills up (epochs.py), and every tool result and file
left in the epoch is sent as a stub (trim.py), the current turn's too, since what made it too large may be there
(a screenshot the user just sent, a browser's screenshots). The call is then made again. Refused again with
nothing new since, the run fails with a plain message.

The small graphs that work for a task, a subagent's and a Home section's, have no epochs to compact: `within_size`
leaves out their tool results and files instead.

The checkpoint keeps every message whole, as always."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from langchain_core.messages import BaseMessage
from langgraph.store.base import BaseStore

from assistant.core.conversation.epochs import compact
from assistant.core.conversation.summary import Summarizer
from assistant.core.conversation.trim import trimmed
from assistant.core.i18n import said
from assistant.core.llm.errors import too_large


class ConversationTooLargeError(Exception):
    def __init__(self) -> None:
        super().__init__(
            said(
                "The model refused the request as too large, even with this conversation compacted and its files "
                "left out. Send a shorter message, or start a new conversation with /clear."
            )
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


async def within_size[R](
    call: Callable[[list[BaseMessage]], Awaitable[R]], messages: Sequence[BaseMessage], before: int
) -> tuple[R, int]:
    """`call`'s result for the messages with the tool results and files before `before` as stubs (trim.py), and that
    point. Refused as too large, it's called once more with every one as a stub, and the point moves to the end, so
    the task's later calls send them as stubs too. Raises what the last call raised."""
    try:
        return await call(trimmed(messages, 0, before)), before
    except Exception as e:
        if not too_large(e) or before >= len(messages):
            raise
    return await call(trimmed(messages, 0, len(messages))), len(messages)
