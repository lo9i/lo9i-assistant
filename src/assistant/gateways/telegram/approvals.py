"""Shows scheduled jobs' approval requests in Telegram (core/approvals.py). The buttons are answered
in handlers.py."""

from typing import Any

from telegram.error import TelegramError

from assistant.core.outbox import DeliveryError
from assistant.gateways.chat.approvals import job_approval_buttons, job_approval_text
from assistant.gateways.telegram.port import TelegramChat
from assistant.gateways.telegram.sender import Recipients
from telegram import Bot


class TelegramApprovals:
    """Registered in the service's approvals while the bot runs (bot.py)."""

    def __init__(self, bot: Bot, service: Recipients) -> None:
        self._bot = bot
        self._service = service

    async def forward(self, interrupt_id: str, title: str, request: dict[str, Any]) -> None:
        recipients = await self._service.telegram_recipients()
        if not recipients:
            raise DeliveryError("No Telegram account is paired.")
        text, buttons = job_approval_text(title, request), job_approval_buttons(interrupt_id)
        try:
            for chat_id in recipients:
                await TelegramChat(self._bot, chat_id).send(text, buttons=buttons)
        except TelegramError as e:
            raise DeliveryError(f"Telegram didn't take the request: {e}") from e
