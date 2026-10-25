"""The doctor's sense of time: the user's day (in their time zone), and the records' times, which the daemon's log
writes in the computer's own."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from assistant.core.config import settings

_LOG_TIME = "%Y-%m-%d %H:%M:%S,%f"
# A turn header's time (core/conversation/turn_header.py::sent_at), in the user's time zone.
_HEADER_TIME = "%Y-%m-%d %H:%M"


def day_of(at: datetime) -> date:
    return at.astimezone(ZoneInfo(settings.timezone)).date()


def log_time(text: str) -> datetime | None:
    """A log record's time; None for text that isn't one (output before the first record)."""
    try:
        return datetime.strptime(text, _LOG_TIME).astimezone()
    except ValueError:
        return None


def header_time(text: str) -> datetime:
    return datetime.strptime(text, _HEADER_TIME).replace(tzinfo=ZoneInfo(settings.timezone))
