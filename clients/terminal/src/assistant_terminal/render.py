"""Prints agent events in the style of Claude Code: a ⏺ bullet per block, replies in gray,
tool calls with their result indented under ⎿."""

import json
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from assistant.core.conversation import choices
from assistant.core.events import (
    ApprovalRequired,
    Cancelled,
    Dispatched,
    Done,
    Error,
    Event,
    TextDelta,
    Thinking,
    ToolFinished,
    ToolStarted,
    Transcribed,
    UserSaid,
)
from assistant_terminal.spinner import Spinner
from assistant_terminal.style import BOLD, DIM, GRAY, RED, RESET, code, paint

_BULLET = "⏺ "
_INDENT = "  "
_RESULT_LINES = 3


@dataclass
class Shown:
    # What the run waits on.
    approvals: list[ApprovalRequired] = field(default_factory=list)
    # Where home sent the message on, to go there after the run.
    dispatched: Dispatched | None = None


async def render(events: AsyncIterator[Event]) -> Shown:
    """Print events and return what the run waits on and where home sent its message on."""
    printer = _Printer()
    shown = Shown()
    spinner = Spinner()
    spinner.start("Thinking")
    async for event in events:
        spinner.stop()
        if isinstance(event, ApprovalRequired):
            shown.approvals.append(event)
        else:
            printer.print(event)
        if isinstance(event, Dispatched):
            shown.dispatched = event
        # While text streams, the text itself shows progress. Otherwise the agent is thinking or running a tool.
        if not isinstance(event, TextDelta):
            spinner.start(f"Running {event.name}" if isinstance(event, ToolStarted) else "Thinking")
    spinner.stop()
    printer.end_text()
    return shown


class _Printer:
    def __init__(self) -> None:
        # What's streaming: "text", "thinking" or "" for nothing.
        self._streaming = ""
        # The streaming reply's text, without the answer buttons' marker.
        self._reply = choices.Streamed()

    def print(self, event: Event) -> None:
        if isinstance(event, TextDelta):
            if self._streaming != "text":
                self._reply = choices.Streamed()
            self._stream("text", f"{code(GRAY)}{_BULLET}", code(GRAY), self._reply.add(event.text))
            return
        if isinstance(event, Thinking):
            self._stream("thinking", f"{code(DIM)}✻ ", code(DIM), event.text)
            return
        self.end_text()
        match event:
            case ToolStarted(name, args, _, within) if within:
                _write(f"{_INDENT}{_BULLET}{name}" + (f"({_describe(args)})" if args else "") + "\n")
            case ToolFinished(_, output, within) if within:
                _write(paint(DIM, _result(output, _INDENT * 2)) + "\n")
            case ToolStarted(name, args):
                _write(f"\n{_BULLET}{paint(BOLD, name)}" + (f"({_describe(args)})" if args else "") + "\n")
            case ToolFinished(_, output):
                _write(paint(DIM, _result(output)) + "\n")
            case Transcribed(text, language):
                _write(paint(DIM, f"{_INDENT}🎤 heard ({language}): {text}") + "\n")
            case UserSaid(text, files):
                attached = "".join(f"  📎 {name}\n" for name in files)
                _write(f"\n{paint(BOLD, '> ' + text)}\n{attached}")
            case Dispatched(line=line):
                _write(f"{_BULLET}{line}\n")
            case Error(message):
                _write(paint(RED, f"\n{_BULLET}Error: {message}") + "\n")
            case Cancelled():
                _write(paint(DIM, f"\n{_BULLET}Stopped.") + "\n")
            case Done():
                pass

    def end_text(self) -> None:
        if self._streaming:
            _write(code(RESET) + "\n")
            self._streaming = ""

    def _stream(self, kind: str, opening: str, color: str, text: str) -> None:
        """Text and thinking stream: an event right after another of its kind continues it."""
        if self._streaming != kind:
            self.end_text()
            _write(f"\n{opening}")
            self._streaming = kind
        _write(color + text.replace("\n", "\n" + _INDENT))


def _describe(args: dict[str, Any]) -> str:
    if len(args) == 1:
        return str(next(iter(args.values())))
    return json.dumps(args, ensure_ascii=False)


def _result(output: str, indent: str = _INDENT) -> str:
    lines = output.strip().splitlines() or ["(no output)"]
    shown = lines[:_RESULT_LINES]
    if len(lines) > _RESULT_LINES:
        shown.append(f"… +{len(lines) - _RESULT_LINES} lines")
    first, *rest = shown
    return "\n".join([f"{indent}⎿  {first}", *(f"{indent}   {line}" for line in rest)])


def _write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
