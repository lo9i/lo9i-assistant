"""A conversation as clients show it: what the user wrote, what the assistant answered, and which
tools it used, each call with its arguments on one line and the start of its output: the whole call loads
when the user opens it (`tool_call`). Turn headers are left out; a quick exchange the inbox carried to the
conversation shows before the message that followed it up (core/conversation/carried.py). A reply of an
agent the conversation was handed to shows its steps as they were shown live: its thinking, its text, each
tool call with its output, and the messages the user sent it while it worked (core/agent_tasks/steps.py). A
delegate call shows the subagent's tool calls inside it, as they streamed live (core/subagent_steps.py)."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.messages.tool import ToolCall

from assistant.core import subagent_steps
from assistant.core.agent_tasks.steps import STEPS, Upload, args_of, files_of, parse
from assistant.core.conversation import carried, ended
from assistant.core.conversation.dispatched import DISPATCH_ID
from assistant.core.conversation.turn_header import is_header
from assistant.core.subagent_steps import SubagentStep

# The most of a call's arguments and of its output history sends: enough to tell what the call was, without
# sending every page or file it read each time a conversation is shown.
_DETAIL = 120
_OUTPUT = 200


@dataclass
class ShownMessage:
    # user | assistant | tool | thinking | carried (Markdown of a quick exchange from the inbox) | notice
    # (background work that ended, which the assistant followed up on unasked)
    role: str
    # A tool's name for a tool.
    text: str
    # A handed-off agent's tool call: what it was about (a command, a file), and its output. A delegate call:
    # its task and the subagent's answer. Any other call of the assistant's: its arguments on one line and the
    # start of its output.
    detail: str = ""
    output: str = ""
    # A delegate call's, or a handed-off agent's call that started a subagent of its own: the subagent's tool
    # calls.
    steps: list[SubagentStep] = field(default_factory=list)
    # The inbox's record of a message it sent on: the message's id, to move it (core/conversation/dispatched.py).
    dispatch_id: str = ""
    # An assistant's tool call: its id, and whether `detail` (its arguments on one line) and `output` leave
    # something out, so the whole call is worth loading (`tool_call`).
    call_id: str = ""
    partial: bool = False


@dataclass
class ShownCall:
    """A tool call of the assistant's in full, loaded when the user opens it."""

    name: str
    args: dict[str, Any]
    output: str


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


def tool_call(messages: Sequence[BaseMessage], call_id: str) -> ShownCall | None:
    """The assistant's call with that id, with all its arguments and its whole output; "" until it has one."""
    calls = (call for m in messages if isinstance(m, AIMessage) for call in m.tool_calls if call["id"] == call_id)
    call = next(calls, None)
    if call is None:
        return None
    result = next((m for m in messages if isinstance(m, ToolMessage) and m.tool_call_id == call_id), None)
    return ShownCall(call["name"], call["args"], result.text if result is not None else "")


def _call(call: ToolCall, result: ToolMessage | None) -> ShownMessage:
    """A tool call; a delegate call with its task, the subagent's steps and its answer, and a task_status call
    that waited with the task's steps and its state."""
    if result is None or not (steps := subagent_steps.of(result)):
        return _preview(call, result)
    about = str(call["args"].get("task") or call["args"].get("task_id", ""))
    return ShownMessage("tool", call["name"], detail=about, output=result.text, steps=steps)


def _preview(call: ToolCall, result: ToolMessage | None) -> ShownMessage:
    """A call with its arguments on one line, as live cards show a lone one (a command, a file), and the start
    of its output."""
    output = result.text if result is not None else ""
    detail, start = _start(_one_line(call["args"]), _DETAIL), _start(output, _OUTPUT)
    # Cards show `detail` as the arguments themselves only when they're one text or number on one line.
    exact = _alone(call["args"]) if call["args"] else ""
    whole = detail == exact and start == output
    return ShownMessage("tool", call["name"], detail, start, call_id=call["id"] or "", partial=not whole)


def _one_line(args: dict[str, Any]) -> str:
    if (alone := _alone(args)) is not None:
        return " ".join(alone.split())
    return ", ".join(f"{name}: {' '.join(_value(value).split())}" for name, value in args.items())


def _alone(args: dict[str, Any]) -> str | None:
    """The call's one argument when it's text or a number, which live cards show as it is."""
    values = list(args.values())
    if len(values) == 1 and isinstance(values[0], str | int | float) and not isinstance(values[0], bool):
        return str(values[0])
    return None


def _value(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _start(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _agent_reply(lines: list[str], reply: str) -> list[ShownMessage]:
    """Its steps, with its own subagents' tool calls inside the call that started them (their words aren't
    shown, as live); the reply after them unless its last text, after the user's last message to it, already
    said it. Its thinking reads as what it says, as it was shown live (core/agent_tasks/steps.py)."""
    shown: list[ShownMessage] = []
    calls: dict[str, ShownMessage] = {}
    steps = [parse(line) for line in lines]
    for line, step in zip(lines, steps, strict=True):
        if within := step.get("within"):
            _add_inner(calls.get(within), step)
        elif step.get("kind") == "user":
            shown.append(ShownMessage("user", _with_attachments(step.get("text", ""), files_of(line))))
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
    else:
        shown.append(ShownMessage("tool", text))


def _with_attachments(text: str, files: list[Upload]) -> str:
    """A message the user sent an agent at work, its files named as a message's are (`_block_text`)."""
    return "\n".join(filter(None, [text, *(f"[attachment {f['name']}]" for f in files)]))


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
