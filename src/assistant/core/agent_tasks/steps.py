"""A task's steps: each line of its progress.log is one step as JSON (docs/agent-plugins.md), the agent's
thinking, what it says, a tool call or a tool call's result. For a conversation handed to the agent they
become the run's events, shown as the assistant's own would be, so the agent's work reads like a reply,
and its thinking reads as what it says: the user hands the conversation over to talk to it;
while task_status waits for a task they show inside that call (`within_call`).
A note, or a plain line from a worker that reports nothing finer, goes inside a call named after the
agent. For the task tools each reads as one line (`line`). The steps of a handed-off reply are kept with
it, in its message's `response_metadata` under STEPS, which no model call sends: history shows them again
(core/conversation/display.py)."""

import json
import uuid
from typing import Any

from assistant.core.events import Event, TextDelta, ToolFinished, ToolStarted

_LINE = 200
# Where a handed-off reply keeps its steps, as the worker wrote them.
STEPS = "agent_steps"


# The words of a text or a thinking as they're written, before the whole of it comes as one step.
_DELTAS = {"text_delta": "text", "thinking_delta": "thinking"}
# A handed-off agent's thinking is shown as what it says.
_SHOWN_AS = {"thinking": "text"}


class AgentSteps:
    def __init__(self, name: str) -> None:
        self._name = name
        # The call that holds the notes, once the first one comes.
        self._notes = ""
        # What was shown last ("text", "tool", ...), to set a new block apart from the one before.
        self._last = ""
        # The text or thinking whose words are streaming now, "" when none is.
        self._open = ""
        # It said something: its reply, its last text, has been shown with it.
        self.spoke = False
        # Every step so far but the streamed words, as written, to keep with the reply.
        self.lines: list[str] = []

    def events(self, message: str) -> list[Event]:
        step = parse(message)
        kind = step.get("kind", "")
        if kind not in _DELTAS:
            self.lines.append(message)
        events = self._events(step)
        if events:
            block = _DELTAS.get(kind, kind)
            self._last = _SHOWN_AS.get(block, block)
        return events

    def reply(self, text: str) -> list[Event]:
        """The reply, when it said nothing else, set apart from the thinking shown before it."""
        if self.spoke:
            return []
        return [TextDelta(("\n\n" if self._last == "text" else "") + text)]

    def end(self, output: str) -> list[Event]:
        """Closes the call that holds the notes, when there is one."""
        return [ToolFinished(self._name, output)] if self._notes else []

    def _events(self, step: dict[str, str]) -> list[Event]:
        kind, text, within = step.get("kind", ""), step.get("text", ""), step.get("within", "")
        block = _DELTAS.get(kind, kind)
        # A subagent's own words aren't forwarded; its tool calls are shown inside the call that started it.
        if block in ("text", "thinking") and within:
            return []
        if block in ("text", "thinking"):
            self.spoke = self.spoke or block == "text"
            return [TextDelta(words) for words in self._words(kind, text)]
        if kind == "tool":
            return [ToolStarted(step.get("tool", ""), _args(step), id=step.get("id", ""), within=within)]
        if kind == "result":
            return [ToolFinished(step.get("tool", ""), text, within=within)]
        return self._note(text)

    def _words(self, kind: str, text: str) -> list[str]:
        """What to show of a text or a thinking: its words as they stream, or the whole of it when none
        streamed. The whole block after its words shows nothing; a new block is a new paragraph."""
        block = _DELTAS.get(kind, kind)
        if kind == block and self._open == block:
            self._open = ""
            return []
        starts = self._open != block
        self._open = block if kind != block else ""
        return [("\n\n" if starts and self._last == "text" else "") + text]

    def _note(self, text: str) -> list[Event]:
        opened: list[Event] = []
        if not self._notes:
            self._notes = f"agent-{uuid.uuid4().hex}"
            opened.append(ToolStarted(self._name, {}, id=self._notes))
        return [*opened, ToolStarted(text, {}, within=self._notes), ToolFinished(text, "", within=self._notes)]


def within_call(message: str, call_id: str) -> list[Event]:
    """A step of a task the assistant follows (task_status waiting for it), shown inside that call: its
    tool calls, results and notes, and what it says as one line. Its thinking and its words as they
    stream aren't; nor are its own subagents' steps."""
    step = parse(message)
    kind = step.get("kind", "")
    if step.get("within"):
        return []
    if kind == "tool":
        return [ToolStarted(step.get("tool", ""), _args(step), id=step.get("id", ""), within=call_id)]
    if kind == "result":
        return [ToolFinished(step.get("tool", ""), step.get("text", ""), within=call_id)]
    if kind in ("note", "text") and (text := line(message)):
        return [ToolStarted(text, {}, within=call_id), ToolFinished(text, "", within=call_id)]
    return []


def streamed(message: str) -> bool:
    """It's the words of a text or a thinking as they stream, which the whole block repeats."""
    return parse(message).get("kind", "") in _DELTAS


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
