"""Keeps the bot's display name in Telegram equal to the assistant's name. The @username stays as
set in BotFather; an unnamed assistant shows the BotFather name."""

import logging
from typing import Protocol

from telegram.error import TelegramError

from telegram import Bot

logger = logging.getLogger(__name__)


class Names(Protocol):
    """The AssistantService call this needs."""

    async def assistant_name(self) -> str: ...


class BotName:
    def __init__(self, service: Names) -> None:
        self._service = service
        self._applied: str | None = None

    def forget(self) -> None:
        """A new bot started; its name is unknown."""
        self._applied = None

    async def apply(self, bot: Bot) -> None:
        """Sets the display name if it changed. Telegram limits how often names change, so only
        real changes are sent; a failure is logged and retried at the next change."""
        name = await self._service.assistant_name()
        if name == self._applied:
            return
        try:
            await bot.set_my_name(name)
        except TelegramError as e:
            logger.warning("Couldn't set the Telegram bot's name to %r: %s", name, e)
            return
        self._applied = name
