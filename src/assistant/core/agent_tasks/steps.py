"""A task's steps: each line of its progress.log is one step as JSON (docs/agent-plugins.md), the agent's
thinking, what it says, a tool call or a tool call's result. For a conversation handed to the agent they
become the run's events, shown as the assistant's own would be, so the agent's work reads like a reply.
A note, or a plain line from a worker that reports nothing finer, goes inside a call named after the
agent. For the task tools each reads as one line (`line`). The steps of a handed-off reply are kept with
it, in its message's `response_metadata` under STEPS, which no model call sends: history shows them again
(core/conversation/display.py)."""

import json
import uuid
from typing import Any

from assistant.core.events import Event, TextDelta, Thinking, ToolFinished, ToolStarted

_LINE = 200
# Where a handed-off reply keeps its steps, as the worker wrote them.
STEPS = "agent_steps"


class AgentSteps:
    def __init__(self, name: str) -> None:
        self._name = name
        # The call that holds the notes, once the first one comes.
        self._notes = ""
        self._in_text = False
        # It said something: its reply, its last text, has been shown with it.
        self.spoke = False
        # Every step so far, as written, to keep with the reply.
        self.lines: list[str] = []

    def events(self, message: str) -> list[Event]:
        self.lines.append(message)
        step = parse(message)
        events = self._events(step)
        self._in_text = step.get("kind") == "text" and bool(events)
        return events

    def end(self, output: str) -> list[Event]:
        """Closes the call that holds the notes, when there is one."""
        return [ToolFinished(self._name, output)] if self._notes else []

    def _events(self, step: dict[str, str]) -> list[Event]:
        kind, text, within = step.get("kind"), step.get("text", ""), step.get("within", "")
        # A subagent's own words aren't forwarded; its tool calls are shown inside the call that started it.
        if kind in ("text", "thinking") and within:
            return []
        if kind == "text":
            self.spoke = True
            return [TextDelta(("\n\n" if self._in_text else "") + text)]
        if kind == "thinking":
            return [Thinking(text)]
        if kind == "tool":
            return [ToolStarted(step.get("tool", ""), _args(step), id=step.get("id", ""), within=within)]
        if kind == "result":
            return [ToolFinished(step.get("tool", ""), text, within=within)]
        return self._note(text)

    def _note(self, text: str) -> list[Event]:
        opened: list[Event] = []
        if not self._notes:
            self._notes = f"agent-{uuid.uuid4().hex}"
            opened.append(ToolStarted(self._name, {}, id=self._notes))
        return [*opened, ToolStarted(text, {}, within=self._notes), ToolFinished(text, "", within=self._notes)]


def line(message: str) -> str:
    """One line for a task's latest steps; "" for steps that don't read as one (thinking, results)."""
    step = parse(message)
    kind, text = step.get("kind"), step.get("text", "").strip()
    if kind == "tool":
        tool, detail = step.get("tool", ""), step.get("detail", "")
        return f"{tool}: {detail}" if detail else tool
    if kind in ("note", "text") and text:
        first = text.splitlines()[0]
        return first if len(first) <= _LINE else first[:_LINE] + "…"
    return ""


def parse(message: str) -> dict[str, str]:
    """A step's fields; a line that isn't a JSON step is a note."""
    try:
        step: Any = json.loads(message)
    except json.JSONDecodeError:
        return {"kind": "note", "text": message}
    if not isinstance(step, dict) or "kind" not in step:
        return {"kind": "note", "text": message}
    return {str(k): str(v) for k, v in step.items()}


def _args(step: dict[str, str]) -> dict[str, Any]:
    """What the call is about (a command, a file): the apps show a call's one argument next to its name."""
    detail = step.get("detail", "")
    return {"detail": detail} if detail else {}
