"""Old tool results: a long epoch keeps resending every email and web page the agent read, long
after it used them. Once the prompt cache has expired, the next call misses it anyway, so from then
on tool results before the last TRIM_KEEP_TURNS user turns are sent as a short stub. The checkpoint
keeps them whole, and the tool call stays, so the agent can call the tool again.

The point is kept in state and only moves forward at a user message, so every call after it sends
the same messages and the cache keeps hitting.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, TypeGuard

from langchain_core.messages import BaseMessage, ToolMessage

from assistant.core.attachments import carries_files
from assistant.core.config import settings
from assistant.core.conversation.epochs import cut_index

# Shorter results cost about as much as their stub.
_MIN_CHARS = 1000


def trim_update(state: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """State update that moves the trim point, when the cache has expired and there's something
    new to trim. The reported token count no longer applies, so it's cleared."""
    if not _cache_expired(state, now):
        return {}
    messages, start = state["messages"], state.get("epoch_start", 0)
    point = cut_index(messages, start, settings.trim_keep_turns)
    since = max(start, state.get("trimmed_before", 0))
    if not any(_trimmable(m) for m in messages[since:point]):
        return {}
    return {"trimmed_before": point, "usage_anchor": None}


def trimmed(messages: Sequence[BaseMessage], start: int, before: int) -> list[BaseMessage]:
    """The messages from `start` as sent to the model: tool results before `before` as stubs."""
    return [_stub(m) if i < before and _trimmable(m) else m for i, m in enumerate(messages[start:], start)]


def _cache_expired(state: Mapping[str, Any], now: datetime) -> bool:
    last = state.get("last_model_call")
    return bool(last) and now - datetime.fromisoformat(last) > timedelta(minutes=settings.prompt_cache_minutes)


def _trimmable(message: BaseMessage) -> TypeGuard[ToolMessage]:
    return isinstance(message, ToolMessage) and (len(message.text) > _MIN_CHARS or carries_files(message))


def _stub(message: ToolMessage) -> ToolMessage:
    text = f"[Left out to save space: {len(message.text)} characters. Call {message.name} again if you need it.]"
    return ToolMessage(text, tool_call_id=message.tool_call_id, name=message.name, status=message.status, id=message.id)
