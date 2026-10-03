"""Plain-text rendering of messages, used as summarizer input and for size estimates."""

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

_MAX_TOOL_OUTPUT = 2000


def render(messages: Sequence[BaseMessage]) -> str:
    return "\n\n".join(text for text in map(_render_message, messages) if text)


def _render_message(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return f"USER: {_text(message.content)}"
    if isinstance(message, AIMessage):
        return _render_ai(message)
    if isinstance(message, ToolMessage):
        return f"TOOL {message.name}:\n{_quote(_truncate(_text(message.content)))}"
    return ""


def _render_ai(message: AIMessage) -> str:
    text = _text(message.content)
    calls = [f"ASSISTANT called {c['name']}({json.dumps(c['args'])})" for c in message.tool_calls]
    if not text:
        return "\n".join(calls)

    return "\n".join([f"ASSISTANT: {text}", *calls])


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(filter(None, (_block_text(b) for b in content)))


def _block_text(block: Any) -> str:
    if isinstance(block, str):
        return block
    if not isinstance(block, dict):
        return ""
    if block.get("type") == "text":
        return block.get("text", "")
    upload = block.get("value", {}).get("upload") if block.get("type") == "non_standard" else None
    return f"[attachment {upload['name']}]" if upload else ""


def _quote(text: str) -> str:
    """Prefixes every line, so text a tool returned can't pass for a USER or ASSISTANT line."""
    return "\n".join(f"| {line}" for line in text.splitlines() or [""])


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_TOOL_OUTPUT else text[:_MAX_TOOL_OUTPUT] + " [truncated]"
