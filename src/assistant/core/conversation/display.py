"""A conversation as clients show it: what the user wrote, what the assistant answered, and which
tools it used. Turn headers and tool outputs are left out. A reply of an agent the conversation was
handed to shows its steps as they were shown live: its thinking, its text, each tool call with its
output (core/agent_tasks/steps.py)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from assistant.core.agent_tasks.steps import STEPS, parse
from assistant.core.conversation.turn_header import is_header


@dataclass
class ShownMessage:
    role: str  # user | assistant | tool | thinking
    # A tool's name for a tool.
    text: str
    # A handed-off agent's tool call: what it was about (a command, a file), and its output.
    detail: str = ""
    output: str = ""


def shown(messages: Sequence[BaseMessage]) -> list[ShownMessage]:
    return [m for message in messages for m in _shown(message)]


def _shown(message: BaseMessage) -> list[ShownMessage]:
    if isinstance(message, HumanMessage):
        return [ShownMessage("user", _text(message.content, skip_header=True))]
    if isinstance(message, AIMessage) and (steps := message.response_metadata.get(STEPS)):
        return _agent_reply(steps, _text(message.content))
    if isinstance(message, AIMessage):
        text = _text(message.content)
        calls = [ShownMessage("tool", call["name"]) for call in message.tool_calls]
        return [*([ShownMessage("assistant", text)] if text else []), *calls]
    return []


def _agent_reply(lines: list[str], reply: str) -> list[ShownMessage]:
    """Its own steps, not its subagents'; the reply after them unless its last text already said it."""
    shown: list[ShownMessage] = []
    for step in (parse(line) for line in lines):
        if not step.get("within"):
            _add_step(shown, step)
    if not any(m.role == "assistant" for m in shown):
        shown.append(ShownMessage("assistant", reply))
    return shown


def _add_step(shown: list[ShownMessage], step: dict[str, str]) -> None:
    kind, text = step.get("kind"), step.get("text", "")
    if kind == "text" and shown and shown[-1].role == "assistant":
        shown[-1].text += f"\n\n{text}"
    elif kind == "text":
        shown.append(ShownMessage("assistant", text))
    elif kind == "thinking":
        shown.append(ShownMessage("thinking", text))
    elif kind == "tool":
        shown.append(ShownMessage("tool", step.get("tool", ""), detail=step.get("detail", "")))
    elif kind == "result":
        _finish(shown, step.get("tool", ""), text)
    else:
        shown.append(ShownMessage("tool", text))


def _finish(shown: list[ShownMessage], tool: str, output: str) -> None:
    """Results carry only the tool's name: they finish its first call still without one."""
    call = next((m for m in shown if m.role == "tool" and m.text == tool and not m.output), None)
    if call is not None:
        call.output = output or "(no output)"


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
