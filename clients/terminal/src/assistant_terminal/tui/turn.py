"""Renders the events of one run into the chat."""

from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from textual.containers import VerticalScroll
from textual.widgets import Markdown
from textual.widgets.markdown import MarkdownStream

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
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.widgets import (
    AssistantMessage,
    ErrorMessage,
    StatusLine,
    StoppedNote,
    ThinkingNote,
    ToolCall,
    TranscriptNote,
    UserMessage,
)

_STOP_HINT = translatable("esc to stop")


class TurnView:
    def __init__(self, chat: VerticalScroll, status: StatusLine) -> None:
        self._chat = chat
        self._status = status
        self._stream: MarkdownStream | None = None
        # The streaming reply's text, without the answer buttons' marker.
        self._shown = choices.Streamed()
        # Tool results carry only the tool name, so match them to calls in order. A subagent's calls
        # are matched within their delegate call, keyed by its id.
        self._pending: dict[str, list[ToolCall]] = defaultdict(list)
        self._calls: dict[str, ToolCall] = {}
        self._steps: dict[tuple[str, str], list[ToolCall]] = defaultdict(list)
        # Where home sent the message on, once the run says so; the app goes there after it.
        self.dispatched: Dispatched | None = None

    async def render(self, events: AsyncIterator[Event]) -> list[ApprovalRequired]:
        """Show the events and return the approvals the run is waiting on."""
        approvals: list[ApprovalRequired] = []
        self._status.show(t("Thinking"), t(_STOP_HINT))
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
            case ToolStarted(name, args, _, within) if within:
                await self._step_started(within, name, args)
            case ToolFinished(name, output, within) if within:
                self._step_finished(within, name, output)
            case ToolStarted(name, args, call_id):
                await self._tool_started(name, args, call_id)
            case ToolFinished(name, output):
                self._tool_finished(name, output)
            case Thinking(text):
                await self._thinking(text)
            case Transcribed(text, language):
                await self._chat.mount(TranscriptNote(text, language))
            case UserSaid(text, files):
                await self._chat.mount(UserMessage(text, files))
            case Dispatched():
                self.dispatched = event
                await self._chat.mount(AssistantMessage(event.line))
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
            self._shown = choices.Streamed()
            self._status.clear()
        if shown := self._shown.add(text):
            await self._stream.write(shown)

    async def _thinking(self, text: str) -> None:
        """Thinking streams: an event right after another continues it."""
        last = self._chat.children[-1] if self._chat.children else None
        if isinstance(last, ThinkingNote):
            last.add(text)
        else:
            await self._chat.mount(ThinkingNote(text))

    async def _end_text(self) -> None:
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None

    async def _tool_started(self, name: str, args: dict[str, Any], call_id: str) -> None:
        call = ToolCall(name, args)
        self._pending[name].append(call)
        self._calls[call_id] = call
        await self._chat.mount(call)
        self._status.show(t("Running {name}", name=name), t(_STOP_HINT))

    async def _step_started(self, within: str, name: str, args: dict[str, Any]) -> None:
        if (call := self._calls.get(within)) is None:
            return
        step = ToolCall(name, args)
        self._steps[within, name].append(step)
        await call.add_step(step)
        self._status.show(t("Running {name}", name=name), t(_STOP_HINT))

    def _step_finished(self, within: str, name: str, output: str) -> None:
        if self._steps[within, name]:
            self._steps[within, name].pop(0).finish(output)

    async def _cancelled(self) -> None:
        for call in [c for calls in [*self._pending.values(), *self._steps.values()] for c in calls]:
            call.cancel()
        self._pending.clear()
        self._steps.clear()
        await self._chat.mount(StoppedNote())

    def _tool_finished(self, name: str, output: str) -> None:
        if self._pending[name]:
            self._pending[name].pop(0).finish(output)
        self._status.show(t("Thinking"), t(_STOP_HINT))
