"""Shows one run's events in a chat: a typing indicator, a status message listing tool calls, the reply
streamed by editing its message, its first message tagged with a short name of the conversation
(`[watchlist] …`), and approval or question buttons. A handed-off agent's thinking isn't shown: a chat has
room only for what's said and done."""

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from assistant.core.channels.chat.approvals import approval_buttons, approval_text
from assistant.core.channels.chat.port import ChatLimits, ChatPort
from assistant.core.channels.chat.questions import question_buttons, question_text
from assistant.core.channels.chat.split import split_text
from assistant.core.conversation import choices
from assistant.core.events import (
    ApprovalRequired,
    Cancelled,
    Dispatched,
    Error,
    Event,
    Held,
    TextDelta,
    ToolFinished,
    ToolStarted,
    Transcribed,
    is_question,
)
from assistant.core.i18n import Texts
from assistant.core.outbox import DeliveryError

_TYPING_SECONDS = 4.0
_DESCRIPTION = 80


class ChatTurn:
    def __init__(self, chat: ChatPort, limits: ChatLimits, t: Texts, thread_id: str = "", tag: str = "") -> None:
        self._chat = chat
        self._t = t
        self._limits = limits
        self._status = _StatusMessage(chat, limits)
        self._reply = _ReplyMessage(chat, limits, f"[{tag}] " if tag else "")
        self._final = ""
        # The conversation the turn runs in.
        self.thread_id = thread_id
        # Where the inbox sent the message on, once the turn says so; the chat goes there after it.
        self.dispatched: Dispatched | None = None

    @property
    def final_text(self) -> str:
        """The reply after the last tool call: the answer, without text written while working."""
        return choices.without_markers(self._final).strip()

    async def render(self, events: AsyncIterator[Event]) -> None:
        typing = asyncio.create_task(self._keep_typing())
        try:
            async for event in events:
                await self._handle(event)
        finally:
            typing.cancel()
            await self._reply.finish()
            await self._status.flush(force=True)

    async def _handle(self, event: Event) -> None:
        match event:
            case TextDelta(text):
                self._final += text
                await self._reply.append(text)
            case ToolStarted(name, args, call_id, within):
                self._final = ""
                await self._after_reply()
                await self._status.started(name, args, call_id, within)
            case ToolFinished(name, _, within):
                await self._status.finished(name, within)
            case ApprovalRequired(interrupt_id, request):
                await self._after_reply()
                await self._ask(interrupt_id, request)
            case Transcribed(text, language):
                heard = text or self._t("(no speech)")
                await self._chat.send(self._t("🎤 I heard ({language}): {text}", language=language, text=heard))
            case Dispatched():
                self.dispatched = event
            case Held():
                await self._chat.send(self._t("⏳ An update is being installed. I'll answer this once it's done."))
            case Error(message):
                await self._chat.send(f"⚠️ {message}")
            case Cancelled():
                await self._chat.send(self._t("⏹ Stopped."))
            case _:
                pass

    async def _ask(self, interrupt_id: str, request: dict[str, Any]) -> None:
        if is_question(request):
            buttons = question_buttons(self._t, interrupt_id, request)
            await self._chat.send(question_text(self._t, request), buttons=buttons)
        else:
            await self._chat.send(approval_text(self._t, request), buttons=approval_buttons(self._t, interrupt_id))

    async def _after_reply(self) -> None:
        """Finish any reply in progress. Tool calls after it go in a new status message, below it."""
        if await self._reply.finish():
            await self._status.flush(force=True)
            self._status = _StatusMessage(self._chat, self._limits)

    async def _keep_typing(self) -> None:
        """A channel that can't show typing, or that went away, ends it; the turn shows it otherwise."""
        with contextlib.suppress(DeliveryError):
            while True:
                await self._chat.typing()
                await asyncio.sleep(_TYPING_SECONDS)


@dataclass
class _Line:
    marker: str
    name: str
    description: str
    call_id: str
    # The call whose subagent made this one; "" for the agent's own.
    within: str


class _StatusMessage:
    """One message listing this turn's tool calls, edited as they start and finish. A subagent's calls
    go indented under the call that started it."""

    def __init__(self, chat: ChatPort, limits: ChatLimits) -> None:
        self._chat = chat
        self._limits = limits
        self._lines: list[_Line] = []
        self._message: str | None = None
        self._last_edit = 0.0

    async def started(self, name: str, args: dict[str, Any], call_id: str = "", within: str = "") -> None:
        line = _Line("⏺", name, _describe(args), call_id, within)
        self._lines.insert(self._place(within), line)
        await self.flush()

    async def finished(self, name: str, within: str = "") -> None:
        for line in self._lines:
            if line.marker == "⏺" and line.name == name and line.within == within:
                line.marker = "✓"
                break
        await self.flush()

    async def flush(self, force: bool = False) -> None:
        if not self._lines or (not force and time.monotonic() - self._last_edit < self._limits.edit_seconds):
            return
        text = "\n".join(self._text(line) for line in self._lines)
        if self._message is None:
            self._message = await self._chat.send(text)
        else:
            await self._chat.edit(self._message, text)
        self._last_edit = time.monotonic()

    def _place(self, within: str) -> int:
        """After the call that started it and the calls already under it; last when it has none."""
        if not within:
            return len(self._lines)
        group = [i for i, line in enumerate(self._lines) if within in (line.call_id, line.within)]
        return group[-1] + 1 if group else len(self._lines)

    def _text(self, line: _Line) -> str:
        indent = "    " if line.within else ""
        return f"{indent}{line.marker} {line.name}({line.description})"


class _ReplyMessage:
    """Streams text by editing one message; the final version is sent as Markdown and split if long. The
    turn's first reply starts with `tag`. The answer buttons' marker never shows (conversation/choices.py)."""

    def __init__(self, chat: ChatPort, limits: ChatLimits, tag: str = "") -> None:
        self._chat = chat
        self._limits = limits
        self._tag = tag
        self._text = ""
        self._message: str | None = None
        self._last_edit = 0.0

    async def append(self, text: str) -> None:
        if not self._text and self._tag:
            text, self._tag = self._tag + text.lstrip(), ""
        self._text += text
        if (
            len(self._text) <= self._limits.draft_limit
            and time.monotonic() - self._last_edit >= self._limits.edit_seconds
        ):
            await self._show_draft()

    async def finish(self) -> bool:
        """Send the final version. Returns whether there was any text."""
        text = choices.without_markers(self._text).strip()
        if text:
            await self._send_final(split_text(text, self._limits.message_limit))
        self._text, self._message = "", None
        return bool(text)

    async def _show_draft(self) -> None:
        draft = choices.without_markers(self._text).strip() + " …"
        if self._message is None:
            self._message = await self._chat.send(draft)
        else:
            await self._chat.edit(self._message, draft)
        self._last_edit = time.monotonic()

    async def _send_final(self, chunks: list[str]) -> None:
        first, *rest = chunks
        if self._message is None:
            await self._chat.send(first, markdown=True)
        else:
            await self._chat.edit(self._message, first, markdown=True)
        for chunk in rest:
            await self._chat.send(chunk, markdown=True)


def _describe(args: dict[str, Any]) -> str:
    text = str(next(iter(args.values()))) if len(args) == 1 else json.dumps(args, ensure_ascii=False)
    return text if len(text) <= _DESCRIPTION else text[: _DESCRIPTION - 3] + "…"
