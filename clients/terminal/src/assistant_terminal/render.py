"""Prints agent events in the style of Claude Code: a ⏺ bullet per block, replies in gray,
tool calls with their result indented under ⎿."""

import json
import sys
from collections.abc import AsyncIterator
from typing import Any

from assistant.core.events import (
    ApprovalRequired,
    Cancelled,
    Done,
    Error,
    Event,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Transcribed,
)
from assistant_terminal.spinner import Spinner
from assistant_terminal.style import BOLD, DIM, GRAY, RED, RESET, code, paint

_BULLET = "⏺ "
_INDENT = "  "
_RESULT_LINES = 3


async def render(events: AsyncIterator[Event]) -> list[ApprovalRequired]:
    """Print events and return the approvals the run is waiting on."""
    printer = _Printer()
    approvals: list[ApprovalRequired] = []
    spinner = Spinner()
    spinner.start("Thinking")
    async for event in events:
        spinner.stop()
        if isinstance(event, ApprovalRequired):
            approvals.append(event)
        else:
            printer.print(event)
        # While text streams, the text itself shows progress. Otherwise the agent is thinking or running a tool.
        if not isinstance(event, TextDelta):
            spinner.start(f"Running {event.name}" if isinstance(event, ToolStarted) else "Thinking")
    spinner.stop()
    printer.end_text()
    return approvals


class _Printer:
    def __init__(self) -> None:
        self._in_text = False

    def print(self, event: Event) -> None:
        if isinstance(event, TextDelta):
            self._text(event.text)
            return
        self.end_text()
        match event:
            case ToolStarted(name, args):
                _write(f"\n{_BULLET}{paint(BOLD, name)}({_describe(args)})\n")
            case ToolFinished(_, output):
                _write(paint(DIM, _result(output)) + "\n")
            case Transcribed(text, language):
                _write(paint(DIM, f"{_INDENT}🎤 heard ({language}): {text}") + "\n")
            case Error(message):
                _write(paint(RED, f"\n{_BULLET}Error: {message}") + "\n")
            case Cancelled():
                _write(paint(DIM, f"\n{_BULLET}Stopped.") + "\n")
            case Done():
                pass

    def end_text(self) -> None:
        if self._in_text:
            _write(code(RESET) + "\n")
            self._in_text = False

    def _text(self, text: str) -> None:
        if not self._in_text:
            _write(f"\n{code(GRAY)}{_BULLET}")
            self._in_text = True
        _write(code(GRAY) + text.replace("\n", "\n" + _INDENT))


def _describe(args: dict[str, Any]) -> str:
    if len(args) == 1:
        return str(next(iter(args.values())))
    return json.dumps(args, ensure_ascii=False)


def _result(output: str) -> str:
    lines = output.strip().splitlines() or ["(no output)"]
    shown = lines[:_RESULT_LINES]
    if len(lines) > _RESULT_LINES:
        shown.append(f"… +{len(lines) - _RESULT_LINES} lines")
    first, *rest = shown
    return "\n".join([f"{_INDENT}⎿  {first}", *(f"{_INDENT}   {line}" for line in rest)])


def _write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
