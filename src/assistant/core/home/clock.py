"""Home's sense of time: the user's day (in their time zone), and whether the last refresh is recent enough."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from assistant.core.config import settings


def day_of(at: datetime) -> date:
    return at.astimezone(ZoneInfo(settings.timezone)).date()


def within(refreshed: datetime | None, now: datetime, minutes: int) -> bool:
    """Refreshed under `minutes` before `now`, on the same day: what was built yesterday is never current today."""
    if refreshed is None:
        return False
    return now - refreshed < timedelta(minutes=minutes) and day_of(refreshed) == day_of(now)
