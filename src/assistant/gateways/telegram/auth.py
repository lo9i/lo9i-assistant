"""Single-user bot: only ids in TELEGRAM_ALLOWED_USER_IDS may use it."""

import logging

from telegram import Update

from assistant.core.config import settings

logger = logging.getLogger(__name__)


def is_allowed(update: Update) -> bool:
    user = update.effective_user
    if user is not None and user.id in settings.telegram_allowed_user_ids:
        return True
    # Logged so the owner can find their id and add it to TELEGRAM_ALLOWED_USER_IDS.
    logger.warning("Ignored Telegram update from user id %s (%s)", user and user.id, user and user.username)
    return False
