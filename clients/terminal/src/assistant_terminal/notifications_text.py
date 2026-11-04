"""Notifications as text, shared by the /notifications screen and the plain REPL."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Notification
from assistant.core.config import settings
from assistant_terminal.i18n import short_date


def notification_line(notification: Notification) -> str:
    """When, what it's about and what it says; a dot for one not read yet."""
    unread = "• " if not notification.read else ""
    return f"{unread}{notified_at(notification)} · {notification.title}: {notification.text}"


def notified_at(notification: Notification) -> str:
    """When it came, in the user's timezone: "Wed 30 Sep 09:00", the same width for every one."""
    return short_date(datetime.fromisoformat(notification.at).astimezone(ZoneInfo(settings.timezone)))
