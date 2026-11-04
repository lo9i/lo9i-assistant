"""The proactive features' sense of time: the user's day and times of day, in their time zone (settings.timezone)."""

from datetime import date, datetime, time, timedelta

from lo9i.core.config import settings
from lo9i.core.jobs.schedule import zone


def local(now: datetime) -> datetime:
    return now.astimezone(zone(settings.timezone))


def day_of(now: datetime) -> str:
    """The user's day, as YYYY-MM-DD."""
    return local(now).date().isoformat()


def at(day: date, hhmm: str) -> datetime:
    """That time of the user's day, as a moment."""
    hours, minutes = map(int, hhmm.split(":"))
    return datetime.combine(day, time(hours, minutes), zone(settings.timezone))


def within_day(now: datetime, start: str, end: str) -> bool:
    """Between two times of the user's day; past midnight when `end` comes before `start`."""
    today = local(now).date()
    begins, ends = at(today, start), at(today, end)
    if ends <= begins:
        return now >= begins or now < ends
    return begins <= now < ends


def stamp(now: datetime) -> str:
    """The time now as the models read it."""
    return f"{local(now):%a %Y-%m-%d %H:%M %Z}"


def days_from(now: datetime, days: int) -> str:
    """The user's day `days` after today (before, when negative), as YYYY-MM-DD."""
    return (local(now).date() + timedelta(days=days)).isoformat()
