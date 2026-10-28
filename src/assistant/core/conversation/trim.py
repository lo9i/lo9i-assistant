"""Old tool results and files: a long epoch keeps resending every email and web page the agent read and
every screenshot the user sent, long after they were used. Once the prompt cache has expired (how long it
lasts depends on the provider, core/llm/choice.py::prompt_cache_minutes), the next call misses it anyway,
so from then on tool results before the last TRIM_KEEP_TURNS user turns are sent as a short stub, and the
files of the user's messages there as a note saying where they're saved. The checkpoint keeps them whole,
and the tool call stays, so the agent can call the tool again.

The point is kept in state and only moves forward at a user message, so every call after it sends
the same messages and the cache keeps hitting.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from assistant.core.attachments import carries_files, carries_user_files, left_out
from assistant.core.config import settings
from assistant.core.conversation.epochs import cut_index

# Shorter results cost about as much as their stub.
_MIN_CHARS = 1000


def trim_update(state: Mapping[str, Any], now: datetime, cache_minutes: float) -> dict[str, Any]:
    """State update that moves the trim point, when the cache, which lasts `cache_minutes` after the
    last model call, has expired and there's something new to trim. The reported token count no longer
    applies, so it's cleared."""
    if not _cache_expired(state, now, cache_minutes):
        return {}
    messages, start = state["messages"], state.get("epoch_start", 0)
    point = cut_index(messages, start, settings.trim_keep_turns)
    since = max(start, state.get("trimmed_before", 0))
    if not any(_trimmable(m) for m in messages[since:point]):
        return {}
    return {"trimmed_before": point, "usage_anchor": None}


def trimmed(messages: Sequence[BaseMessage], start: int, before: int) -> list[BaseMessage]:
    """The messages from `start` as sent to the model: tool results and the user's files before `before` as stubs."""
    return [_stub(m) if i < before and _trimmable(m) else m for i, m in enumerate(messages[start:], start)]


def _cache_expired(state: Mapping[str, Any], now: datetime, cache_minutes: float) -> bool:
    last = state.get("last_model_call")
    return bool(last) and now - datetime.fromisoformat(last) > timedelta(minutes=cache_minutes)


def _trimmable(message: BaseMessage) -> bool:
    if isinstance(message, ToolMessage):
        return len(message.text) > _MIN_CHARS or carries_files(message)
    return carries_user_files(message)


def _stub(message: BaseMessage) -> BaseMessage:
    if isinstance(message, HumanMessage):
        return left_out(message)
    return _tool_stub(message) if isinstance(message, ToolMessage) else message


def _tool_stub(message: ToolMessage) -> ToolMessage:
    text = f"[Left out to save space: {len(message.text)} characters. Call {message.name} again if you need it.]"
    return ToolMessage(text, tool_call_id=message.tool_call_id, name=message.name, status=message.status, id=message.id)
