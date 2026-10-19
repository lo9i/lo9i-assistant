"""Notifications as text, shared by the /notifications screen and the plain REPL."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Notification
from assistant.core.config import settings


def notification_line(notification: Notification) -> str:
    """When, what it's about and what it says; a dot for one not read yet."""
    local = datetime.fromisoformat(notification.at).astimezone(ZoneInfo(settings.timezone))
    unread = "• " if not notification.read else ""
    return f"{unread}{local:%a %d %b %H:%M} · {notification.title}: {notification.text}"
