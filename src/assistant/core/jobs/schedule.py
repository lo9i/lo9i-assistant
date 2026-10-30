"""Cron schedule math in the job's time zone."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, croniter

from assistant.core.i18n import said


class ScheduleError(Exception):
    pass


def validate(schedule: str, timezone: str) -> None:
    if not croniter.is_valid(schedule):
        raise ScheduleError(
            said("Not a valid cron schedule: {schedule!r} (e.g. '0 9 * * *' for every day at 09:00)", schedule=schedule)
        )
    zone(timezone)


def zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ScheduleError(said("Unknown time zone: {timezone}", timezone=timezone)) from e


def next_runs(schedule: str, timezone: str, after: datetime, count: int = 1) -> list[datetime]:
    """The next `count` run times after `after`, as timezone-aware datetimes in `timezone`."""
    try:
        it = croniter(schedule, after.astimezone(ZoneInfo(timezone)))
    except CroniterBadCronError as e:
        raise ScheduleError(str(e)) from e
    return [it.get_next(datetime) for _ in range(count)]


def describe(schedule: str, timezone: str, after: datetime) -> str:
    """The next three runs in plain words, so a wrong schedule is easy to spot."""
    runs = ", ".join(t.strftime("%a %d %b %H:%M") for t in next_runs(schedule, timezone, after, 3))
    return f"next runs: {runs} ({timezone})"


def parse_at(at: str, timezone: str, now: datetime) -> datetime:
    """A one-time run's moment, given as local time in `timezone` (e.g. 2026-09-30T14:05).
    Raises ScheduleError when it can't be read or has already passed."""
    try:
        moment = datetime.fromisoformat(at)
    except ValueError as e:
        raise ScheduleError(said("Not a date and time: {at!r} (e.g. 2026-09-30T14:05)", at=at)) from e
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone(timezone))
    if moment <= now:
        raise ScheduleError(said("{at} has already passed.", at=at))
    return moment


def describe_once(moment: datetime, timezone: str) -> str:
    return f"runs once at {moment.astimezone(ZoneInfo(timezone)).strftime('%a %d %b %H:%M')} ({timezone})"
