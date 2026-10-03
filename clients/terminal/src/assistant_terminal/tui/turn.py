"""Renders the events of one run into the chat."""

from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from textual.containers import VerticalScroll
from textual.widgets import Markdown
from textual.widgets.markdown import MarkdownStream

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
from assistant_terminal.tui.widgets import (
    AssistantMessage,
    ErrorMessage,
    StatusLine,
    StoppedNote,
    ToolCall,
    TranscriptNote,
)

_STOP_HINT = "esc to stop"


class TurnView:
    def __init__(self, chat: VerticalScroll, status: StatusLine) -> None:
        self._chat = chat
        self._status = status
        self._stream: MarkdownStream | None = None
        # Tool results carry only the tool name, so match them to calls in order.
        self._pending: dict[str, list[ToolCall]] = defaultdict(list)

    async def render(self, events: AsyncIterator[Event]) -> list[ApprovalRequired]:
        """Show the events and return the approvals the run is waiting on."""
        approvals: list[ApprovalRequired] = []
        self._status.show("Thinking", _STOP_HINT)
        try:
            async for event in events:
                if isinstance(event, ApprovalRequired):
                    approvals.append(event)
                else:
                    await self._handle(event)
        finally:
            await self._end_text()
            self._status.clear()
        return approvals

    async def _handle(self, event: Event) -> None:
        if isinstance(event, TextDelta):
            await self._text(event.text)
            return
        await self._end_text()
        match event:
            case ToolStarted(name, args):
                await self._tool_started(name, args)
            case ToolFinished(name, output):
                self._tool_finished(name, output)
            case Transcribed(text, language):
                await self._chat.mount(TranscriptNote(text, language))
            case Error(message):
                await self._chat.mount(ErrorMessage(message))
            case Cancelled():
                await self._cancelled()
            case Done():
                pass

    async def _text(self, text: str) -> None:
        if self._stream is None:
            message = AssistantMessage()
            await self._chat.mount(message)
            self._stream = Markdown.get_stream(message)
            self._status.clear()
        await self._stream.write(text)

    async def _end_text(self) -> None:
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None

    async def _tool_started(self, name: str, args: dict[str, Any]) -> None:
        call = ToolCall(name, args)
        self._pending[name].append(call)
        await self._chat.mount(call)
        self._status.show(f"Running {name}", _STOP_HINT)

    async def _cancelled(self) -> None:
        for call in [c for calls in self._pending.values() for c in calls]:
            call.cancel()
        self._pending.clear()
        await self._chat.mount(StoppedNote())

    def _tool_finished(self, name: str, output: str) -> None:
        if self._pending[name]:
            self._pending[name].pop(0).finish(output)
        self._status.show("Thinking", _STOP_HINT)
