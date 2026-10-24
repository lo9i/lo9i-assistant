"""A conversation as clients show it: what the user wrote, what the assistant answered, and which
tools it used. Turn headers and tool outputs are left out; a quick exchange the inbox carried to the
conversation shows before the message that followed it up (core/conversation/carried.py). A reply of an
agent the conversation was handed to shows its steps as they were shown live: its thinking, its text, each
tool call with its output, and the messages the user sent it while it worked (core/agent_tasks/steps.py). A
delegate call shows the subagent's tool calls inside it, as they streamed live (core/subagent_steps.py)."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.messages.tool import ToolCall

from assistant.core import subagent_steps
from assistant.core.agent_tasks.steps import STEPS, args_of, parse
from assistant.core.conversation import carried, ended
from assistant.core.conversation.dispatched import DISPATCH_ID
from assistant.core.conversation.turn_header import is_header
from assistant.core.subagent_steps import SubagentStep


@dataclass
class ShownMessage:
    # user | assistant | tool | thinking | carried (Markdown of a quick exchange from the inbox) | notice
    # (background work that ended, which the assistant followed up on unasked)
    role: str
    # A tool's name for a tool.
    text: str
    # A handed-off agent's tool call: what it was about (a command, a file), and its output. A delegate call:
    # its task and the subagent's answer.
    detail: str = ""
    output: str = ""
    # A delegate call's, or a handed-off agent's call that started a subagent of its own: the subagent's tool
    # calls.
    steps: list[SubagentStep] = field(default_factory=list)
    # The inbox's record of a message it sent on: the message's id, to move it (core/conversation/dispatched.py).
    dispatch_id: str = ""


def shown(messages: Sequence[BaseMessage]) -> list[ShownMessage]:
    results = {m.tool_call_id: m for m in messages if isinstance(m, ToolMessage)}
    return [m for message in messages for m in _shown(message, results)]


def _shown(message: BaseMessage, results: dict[str, ToolMessage]) -> list[ShownMessage]:
    if isinstance(message, HumanMessage) and (notice := ended.follow_up_notice(message)):
        return [ShownMessage("notice", notice)]
    if isinstance(message, HumanMessage):
        exchange = carried.of(message)
        before = [ShownMessage("carried", carried.shown(exchange))] if exchange else []
        return [*before, ShownMessage("user", _text(message.content, skip_header=True))]
    if isinstance(message, AIMessage) and (steps := message.response_metadata.get(STEPS)):
        return _agent_reply(steps, _text(message.content))
    if isinstance(message, AIMessage):
        text = _text(message.content)
        calls = [_call(call, results.get(call["id"] or "")) for call in message.tool_calls]
        said = ShownMessage("assistant", text, dispatch_id=message.response_metadata.get(DISPATCH_ID, ""))
        return [*([said] if text else []), *calls]
    return []


def _call(call: ToolCall, result: ToolMessage | None) -> ShownMessage:
    """A tool call; a delegate call with its task, the subagent's steps and its answer."""
    if result is None or not (steps := subagent_steps.of(result)):
        return ShownMessage("tool", call["name"])
    task = str(call["args"].get("task", ""))
    return ShownMessage("tool", call["name"], detail=task, output=result.text, steps=steps)


def _agent_reply(lines: list[str], reply: str) -> list[ShownMessage]:
    """Its steps, with its own subagents' tool calls inside the call that started them (their words aren't
    shown, as live); the reply after them unless its last text, after the user's last message to it, already
    said it. Its thinking reads as what it says, as it was shown live (core/agent_tasks/steps.py)."""
    shown: list[ShownMessage] = []
    calls: dict[str, ShownMessage] = {}
    steps = [parse(line) for line in lines]
    for step in steps:
        if within := step.get("within"):
            _add_inner(calls.get(within), step)
        else:
            _add_step(shown, step, calls)
    own = [step for step in steps if not step.get("within")]
    last_message = max((i for i, step in enumerate(own) if step.get("kind") == "user"), default=-1)
    if not any(step.get("kind") == "text" for step in own[last_message + 1 :]):
        _add_step(shown, {"kind": "text", "text": reply}, calls)
    return shown


def _add_step(shown: list[ShownMessage], step: dict[str, str], calls: dict[str, ShownMessage]) -> None:
    kind, text = step.get("kind"), step.get("text", "")
    if kind in ("text", "thinking") and shown and shown[-1].role == "assistant":
        shown[-1].text += f"\n\n{text}"
    elif kind in ("text", "thinking"):
        shown.append(ShownMessage("assistant", text))
    elif kind == "tool":
        shown.append(call := ShownMessage("tool", step.get("tool", ""), detail=step.get("detail", "")))
        calls[step.get("id") or f"#{len(calls)}"] = call
    elif kind == "result":
        _finish(shown, step.get("tool", ""), text)
    elif kind == "user":
        shown.append(ShownMessage("user", text))
    else:
        shown.append(ShownMessage("tool", text))


def _add_inner(call: ShownMessage | None, step: dict[str, str]) -> None:
    """A step of the agent's own subagent: its tool calls go inside the call that started it."""
    if call is None:
        return
    name = step.get("tool", "")
    if step.get("kind") == "tool":
        call.steps.append(SubagentStep(name, args_of(step), ""))
    elif step.get("kind") == "result":
        index = next((i for i, s in enumerate(call.steps) if s.name == name and not s.output), None)
        if index is not None:
            call.steps[index] = SubagentStep(name, call.steps[index].args, step.get("text", "") or "(no output)")


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
