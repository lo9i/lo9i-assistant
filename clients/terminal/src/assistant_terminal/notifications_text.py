"""Notifications as text, shared by the /notifications screen and the plain REPL."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Notification
from assistant.core.config import settings
from assistant_terminal.i18n import short_date


def notification_line(notification: Notification) -> str:
    """When, what it's about and what it says; a dot for one not read yet."""
    local = datetime.fromisoformat(notification.at).astimezone(ZoneInfo(settings.timezone))
    unread = "• " if not notification.read else ""
    return f"{unread}{short_date(local)} · {notification.title}: {notification.text}"
