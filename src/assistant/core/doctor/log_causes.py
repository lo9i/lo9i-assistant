"""The day's problems in the daemon's log: its records at WARNING or above in errors.log and daemon.log
(core/logs/), across their rotated parts, each record once. A record's cause is the last exception line of its
traceback and the last frame in lo9i's own code; a record without one is its first line, where its logger is."""

import re
from collections.abc import Iterator
from datetime import date, datetime

from assistant.core.doctor.causes import Occurrence
from assistant.core.doctor.clock import day_of, log_time
from assistant.core.logs import LOG_FILES, LogEntry, LogFile, parse
from assistant.core.logs.entries import at_least

_LEVEL = "WARNING"
# Errors are in both files: errors.log keeps them after daemon.log rotated them away.
_FILES = ("errors", "daemon")
_FRAME = re.compile(r'^\s*File "(?P<path>[^"]+)", line \d+, in (?P<function>.+)$')
# A frame in lo9i's own code, by its package's folder.
_OWN = "/assistant/"
# Lines an exception group draws its parts with ("  | ").
_BOX = re.compile(r"^(?:\s*\|)+ ?")


def day_occurrences(day: date) -> list[Occurrence]:
    """Blocking: reads the files."""
    seen: dict[tuple[str, str, str], tuple[LogEntry, datetime]] = {}
    for name in _FILES:
        for entry, at in _day_records(LOG_FILES[name], day):
            seen.setdefault((entry.time, entry.logger, entry.message.partition("\n")[0]), (entry, at))
    return [occurrence(entry, at) for entry, at in seen.values()]


def occurrence(entry: LogEntry, at: datetime) -> Occurrence:
    lines = [_BOX.sub("", line) for line in entry.message.splitlines()] or [""]
    frames = [(i, match) for i, line in enumerate(lines) if (match := _FRAME.match(line))]
    if not frames:
        return Occurrence(lines[0], entry.logger, at, entry.level, entry.message)
    after = lines[frames[-1][0] + 1 :]
    title = next((line for line in after if line and not line[0].isspace()), lines[0])
    own = [match for _, match in frames if _OWN in match["path"]]
    where = _frame(own[-1]) if own else entry.logger
    return Occurrence(title, where, at, entry.level, entry.message)


def _day_records(file: LogFile, day: date) -> Iterator[tuple[LogEntry, datetime]]:
    """Newest part first; a part that starts before the day is the last one read."""
    for path in file.paths():
        try:
            text = path.read_text(errors="replace")
        except FileNotFoundError:
            continue
        records = [(entry, at) for entry in parse(text) if (at := log_time(entry.time)) is not None]
        yield from ((entry, at) for entry, at in records if at_least(entry, _LEVEL) and day_of(at) == day)
        if records and day_of(records[0][1]) < day:
            return


def _frame(match: re.Match[str]) -> str:
    path = match["path"]
    return f"{path[path.rindex(_OWN) + 1 :]} in {match['function']}"
