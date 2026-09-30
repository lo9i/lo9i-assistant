"""Shows one run's events in Telegram: a typing indicator, a status message listing tool calls,
the reply streamed by editing its message, and approval buttons."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from assistant.core.events import ApprovalRequired, Done, Error, Event, TextDelta, ToolFinished, ToolStarted, Transcribed
from assistant.gateways.telegram.approvals import approval_buttons, approval_text
from assistant.gateways.telegram.formatting import split_text
from assistant.gateways.telegram.port import ChatPort

# Telegram allows about one edit per second in a chat.
_EDIT_INTERVAL = 1.0
_TYPING_INTERVAL = 4.0
_STREAM_LIMIT = 3500


class TelegramTurn:
    def __init__(self, chat: ChatPort) -> None:
        self._chat = chat
        self._status = _StatusMessage(chat)
        self._reply = _ReplyMessage(chat)

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
                await self._reply.append(text)
            case ToolStarted(name, args):
                await self._after_reply()
                await self._status.started(name, args)
            case ToolFinished(name, _):
                await self._status.finished(name)
            case ApprovalRequired(interrupt_id, request):
                await self._after_reply()
                await self._chat.send(approval_text(request), buttons=approval_buttons(interrupt_id))
            case Transcribed(text, language):
                await self._chat.send(f"🎤 I heard ({language}): {text or '(no speech)'}")
            case Error(message):
                await self._chat.send(f"⚠️ {message}")
            case Done():
                pass

    async def _after_reply(self) -> None:
        """Finish any reply in progress. Tool calls after it go in a new status message, below it."""
        if await self._reply.finish():
            await self._status.flush(force=True)
            self._status = _StatusMessage(self._chat)

    async def _keep_typing(self) -> None:
        while True:
            await self._chat.typing()
            await asyncio.sleep(_TYPING_INTERVAL)


class _StatusMessage:
    """One message listing this turn's tool calls, edited as they start and finish."""

    def __init__(self, chat: ChatPort) -> None:
        self._chat = chat
        self._lines: list[list[str]] = []  # [marker, name, description]
        self._message_id: int | None = None
        self._last_edit = 0.0

    async def started(self, name: str, args: dict[str, Any]) -> None:
        self._lines.append(["⏺", name, _describe(args)])
        await self.flush()

    async def finished(self, name: str) -> None:
        for line in self._lines:
            if line[0] == "⏺" and line[1] == name:
                line[0] = "✓"
                break
        await self.flush()

    async def flush(self, force: bool = False) -> None:
        if not self._lines or (not force and time.monotonic() - self._last_edit < _EDIT_INTERVAL):
            return
        text = "\n".join(f"{marker} {name}({description})" for marker, name, description in self._lines)
        if self._message_id is None:
            self._message_id = await self._chat.send(text)
        else:
            await self._chat.edit(self._message_id, text)
        self._last_edit = time.monotonic()


class _ReplyMessage:
    """Streams text by editing one message; the final version is sent as Markdown and split if long."""

    def __init__(self, chat: ChatPort) -> None:
        self._chat = chat
        self._text = ""
        self._message_id: int | None = None
        self._last_edit = 0.0

    async def append(self, text: str) -> None:
        self._text += text
        if len(self._text) <= _STREAM_LIMIT and time.monotonic() - self._last_edit >= _EDIT_INTERVAL:
            await self._show_draft()

    async def finish(self) -> bool:
        """Send the final version. Returns whether there was any text."""
        text = self._text.strip()
        if text:
            await self._send_final(split_text(text))
        self._text, self._message_id = "", None
        return bool(text)

    async def _show_draft(self) -> None:
        draft = self._text.strip() + " …"
        if self._message_id is None:
            self._message_id = await self._chat.send(draft)
        else:
            await self._chat.edit(self._message_id, draft)
        self._last_edit = time.monotonic()

    async def _send_final(self, chunks: list[str]) -> None:
        first, *rest = chunks
        if self._message_id is None:
            await self._chat.send(first, markdown=True)
        else:
            await self._chat.edit(self._message_id, first, markdown=True)
        for chunk in rest:
            await self._chat.send(chunk, markdown=True)


def _describe(args: dict[str, Any]) -> str:
    text = str(next(iter(args.values()))) if len(args) == 1 else json.dumps(args, ensure_ascii=False)
    return text if len(text) <= 80 else text[:77] + "…"
