"""Delivers messages the agent starts (send_message) to the paired Telegram accounts."""

from typing import Protocol

from telegram.error import TelegramError

from assistant.core.outbox import DeliveryError
from assistant.gateways.chat.split import split_text
from assistant.gateways.telegram.formatting import CHUNK
from assistant.gateways.telegram.port import TelegramChat
from telegram import Bot


class Recipients(Protocol):
    """The AssistantService call the sender needs."""

    async def telegram_recipients(self) -> list[int]: ...


class TelegramSender:
    """Registered in the service's outbox while the bot runs (bot.py)."""

    def __init__(self, bot: Bot, service: Recipients) -> None:
        self._bot = bot
        self._service = service

    async def send(self, text: str) -> None:
        recipients = await self._service.telegram_recipients()
        if not recipients:
            raise DeliveryError("No Telegram account is paired yet. The user can pair one with /telegram.")
        try:
            for chat_id in recipients:
                await self._send_to(chat_id, text)
        except TelegramError as e:
            raise DeliveryError(f"Telegram didn't take the message: {e}") from e

    async def _send_to(self, chat_id: int, text: str) -> None:
        chat = TelegramChat(self._bot, chat_id)
        for part in split_text(text, CHUNK):
            await chat.send(part, markdown=True)
