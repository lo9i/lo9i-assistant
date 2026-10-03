"""ChatPort for Telegram (see gateways/chat/port.py), and the limits a turn keeps there."""

import logging

from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest

from assistant.gateways.chat.port import Buttons
from assistant.gateways.chat.turn import Limits
from assistant.gateways.telegram.formatting import CHUNK, to_markdown_v2
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# Telegram allows about one edit per second in a chat.
LIMITS = Limits(edit_interval=1.0, stream_limit=CHUNK, chunk=CHUNK)


class TelegramChat:
    """ChatPort for one chat. Markdown that Telegram rejects is resent as plain text."""

    def __init__(self, bot: Bot, chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def send(self, text: str, *, markdown: bool = False, buttons: Buttons | None = None) -> int:
        markup = (
            InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data) for label, data in buttons]])
            if buttons
            else None
        )
        try:
            body, parse_mode = _formatted(text, markdown)
            message = await self._bot.send_message(self._chat_id, body, parse_mode=parse_mode, reply_markup=markup)
        except BadRequest:
            message = await self._bot.send_message(self._chat_id, text, reply_markup=markup)
        return message.message_id

    async def edit(self, message_id: int, text: str, *, markdown: bool = False) -> None:
        try:
            body, parse_mode = _formatted(text, markdown)
            await self._bot.edit_message_text(body, chat_id=self._chat_id, message_id=message_id, parse_mode=parse_mode)
        except BadRequest as e:
            if "not modified" in str(e):
                return
            await self._edit_plain(message_id, text)

    async def typing(self) -> None:
        await self._bot.send_chat_action(self._chat_id, ChatAction.TYPING)

    async def send_voice(self, ogg_opus: bytes) -> None:
        await self._bot.send_voice(self._chat_id, ogg_opus)

    async def _edit_plain(self, message_id: int, text: str) -> None:
        try:
            await self._bot.edit_message_text(text, chat_id=self._chat_id, message_id=message_id)
        except BadRequest as e:
            logger.warning("Telegram edit failed: %s", e)


def _formatted(text: str, markdown: bool) -> tuple[str, ParseMode | None]:
    return (to_markdown_v2(text), ParseMode.MARKDOWN_V2) if markdown else (text, None)
