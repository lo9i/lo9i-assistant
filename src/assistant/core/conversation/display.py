"""A conversation as clients show it: what the user wrote, what the assistant answered, and which
tools it used. Turn headers and tool outputs are left out."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from assistant.core.conversation.turn_header import is_header


@dataclass
class ShownMessage:
    role: str  # user | assistant | tool
    text: str


def shown(messages: Sequence[BaseMessage]) -> list[ShownMessage]:
    return [m for message in messages for m in _shown(message)]


def _shown(message: BaseMessage) -> list[ShownMessage]:
    if isinstance(message, HumanMessage):
        return [ShownMessage("user", _text(message.content, skip_header=True))]
    if isinstance(message, AIMessage):
        text = _text(message.content)
        calls = [ShownMessage("tool", call["name"]) for call in message.tool_calls]
        return [*([ShownMessage("assistant", text)] if text else []), *calls]
    return []


def _text(content: Any, skip_header: bool = False) -> str:
    if isinstance(content, str):
        return content
    blocks = [b for b in content if not (skip_header and is_header(b))]
    return "\n".join(filter(None, map(_block_text, blocks))).strip()


def _block_text(block: Any) -> str:
    if isinstance(block, str):
        return block
    if not isinstance(block, dict):
        return ""
    if block.get("type") == "text":
        return block.get("text", "")
    upload = block.get("value", {}).get("upload") if block.get("type") == "non_standard" else None
    return f"[attachment {upload['name']}]" if upload else ""
