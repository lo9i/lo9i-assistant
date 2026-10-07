"""Log entries: one record as the daemon writes it (`FORMAT`), read back from its text. A record's
first line starts with its time, level and logger; the lines after it (a traceback) belong to it."""

import re
from dataclasses import dataclass
from typing import Literal

from assistant.core.logs.components import component_of

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
# Lowest first. CRITICAL is shown with the errors.
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

_FIRST_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) (DEBUG|INFO|WARNING|ERROR|CRITICAL) (\S+): (.*)$", re.DOTALL
)


@dataclass
class LogEntry:
    """One record. `message` keeps every line of it. Text before the first record of a file (output
    that isn't a record) has no time, level or logger."""

    time: str
    level: str
    logger: str
    component: str
    message: str


def parse(text: str) -> list[LogEntry]:
    entries: list[LogEntry] = []
    for line in text.splitlines():
        if (entry := _record(line)) is not None:
            entries.append(entry)
        elif entries:
            entries[-1].message += "\n" + line
        else:
            entries.append(LogEntry("", "", "", component_of(""), line))
    return entries


def parse_record(text: str) -> LogEntry:
    """One formatted record, which may span lines."""
    first, _, rest = text.partition("\n")
    entry = _record(first) or LogEntry("", "", "", component_of(""), first)
    if rest:
        entry.message += "\n" + rest
    return entry


def at_least(entry: LogEntry, level: str) -> bool:
    return entry.level in LEVELS and LEVELS.index(entry.level) >= LEVELS.index(level)


def _record(line: str) -> LogEntry | None:
    match = _FIRST_LINE.match(line)
    if match is None:
        return None
    time, level, logger, message = match.groups()
    return LogEntry(time, level, logger, component_of(logger), message)
