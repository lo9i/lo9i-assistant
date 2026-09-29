"""The Telegram operations a turn needs, behind a small interface so rendering can be tested without Telegram."""

import logging
from typing import Protocol

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest

from assistant.gateways.telegram.formatting import to_markdown_v2

logger = logging.getLogger(__name__)

Buttons = list[tuple[str, str]]  # (label, callback data)


class ChatPort(Protocol):
    async def send(self, text: str, *, markdown: bool = False, buttons: Buttons | None = None) -> int: ...
    async def edit(self, message_id: int, text: str, *, markdown: bool = False) -> None: ...
    async def typing(self) -> None: ...


class TelegramChat:
    """ChatPort for one chat. Markdown that Telegram rejects is resent as plain text."""

    def __init__(self, bot: Bot, chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def send(self, text: str, *, markdown: bool = False, buttons: Buttons | None = None) -> int:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data) for label, data in buttons]]) if buttons else None
        try:
            message = await self._bot.send_message(self._chat_id, *_formatted(text, markdown), reply_markup=markup)
        except BadRequest:
            message = await self._bot.send_message(self._chat_id, text, reply_markup=markup)
        return message.message_id

    async def edit(self, message_id: int, text: str, *, markdown: bool = False) -> None:
        try:
            await self._bot.edit_message_text(*_formatted(text, markdown), chat_id=self._chat_id, message_id=message_id)
        except BadRequest as e:
            if "not modified" in str(e):
                return
            await self._edit_plain(message_id, text)

    async def typing(self) -> None:
        await self._bot.send_chat_action(self._chat_id, ChatAction.TYPING)

    async def _edit_plain(self, message_id: int, text: str) -> None:
        try:
            await self._bot.edit_message_text(text, chat_id=self._chat_id, message_id=message_id)
        except BadRequest as e:
            logger.warning("Telegram edit failed: %s", e)


def _formatted(text: str, markdown: bool) -> tuple[str, ParseMode | None]:
    return (to_markdown_v2(text), ParseMode.MARKDOWN_V2) if markdown else (text, None)
