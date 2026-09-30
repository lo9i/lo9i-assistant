"""Who may use the bot: accounts paired from the app with a one-time code."""

import logging

from telegram import Update

from assistant.core.agent import AssistantService

logger = logging.getLogger(__name__)

_PAIRED = "Paired ✓. You can talk to the assistant here now. /new starts a new conversation."


async def is_allowed(service: AssistantService, update: Update) -> bool:
    user = update.effective_user
    if user is not None and await service.telegram_allowed(user.id):
        return True
    logger.info("Ignored Telegram update from user id %s", user and user.id)
    return False


async def try_pairing(service: AssistantService, update: Update) -> bool:
    """Pairs the sender when the message holds the open pairing code, and confirms in the chat."""
    user, message = update.effective_user, update.effective_message
    if user is None or message is None or not message.text:
        return False
    if not await service.pair_telegram_user(message.text, user.id, _display_name(user)):
        return False
    await message.reply_text(_PAIRED)
    return True


def _display_name(user) -> str:
    return f"{user.full_name} (@{user.username})" if user.username else user.full_name
