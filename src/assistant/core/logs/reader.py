"""Reading the latest entries of a log file that match a query, across its rotated parts. The parts
are opened first and read up to where they ended then, so a reader that follows the file from that
moment (writer.py) misses and repeats nothing."""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from typing import BinaryIO

from assistant.core.i18n import said
from assistant.core.logs.components import COMPONENTS
from assistant.core.logs.entries import LEVELS, LogEntry, at_least, parse
from assistant.core.logs.files import LogFile, LogFileInfo, info

MAX_LINES = 1000


class LogQueryError(ValueError):
    """An unknown level or component, or a number of entries out of range."""


@dataclass(frozen=True)
class LogQuery:
    """Entries at `level` or above ("" for every level) from `component` ("" for all), the latest `lines`."""

    level: str = ""
    component: str = ""
    lines: int = 100

    def __post_init__(self) -> None:
        if self.level and self.level not in LEVELS:
            raise LogQueryError(said("Unknown level: {level}", level=self.level))
        if self.component and self.component not in COMPONENTS:
            raise LogQueryError(said("Unknown component: {component}", component=self.component))
        if not 1 <= self.lines <= MAX_LINES:
            raise LogQueryError(said("Lines must be between 1 and {count}.", count=MAX_LINES))

    def matches(self, entry: LogEntry) -> bool:
        if self.component and entry.component != self.component:
            return False
        return not self.level or at_least(entry, self.level)


@dataclass
class LogPage:
    """The latest matching entries, oldest first."""

    file: LogFileInfo
    entries: list[LogEntry]


@dataclass
class OpenPart:
    """One part of a log file, open, and how far it went when it was opened."""

    stream: BinaryIO
    end: int


def open_parts(file: LogFile) -> list[OpenPart]:
    """Blocking. Newest first; parts that don't exist are left out."""
    parts = []
    for path in file.paths():
        try:
            stream = path.open("rb")
        except FileNotFoundError:
            continue
        parts.append(OpenPart(stream, stream.seek(0, 2)))
    return parts


def close_parts(parts: Iterable[OpenPart]) -> None:
    for part in parts:
        part.stream.close()


def latest(parts: list[OpenPart], query: LogQuery) -> list[LogEntry]:
    """Blocking. Reads newer parts first and stops once it has enough."""
    found: list[LogEntry] = []
    for part in parts:
        part.stream.seek(0)
        text = part.stream.read(part.end).decode(errors="replace")
        matching = [e for e in parse(text) if query.matches(e)]
        found = matching[-(query.lines - len(found)) :] + found
        if len(found) >= query.lines:
            break
    return found


async def read_page(file: LogFile, query: LogQuery) -> LogPage:
    return await asyncio.to_thread(_page, file, query)


def page_of(file: LogFile, parts: list[OpenPart], query: LogQuery) -> LogPage:
    """Blocking."""
    return LogPage(info(file), latest(parts, query))


def _page(file: LogFile, query: LogQuery) -> LogPage:
    parts = open_parts(file)
    try:
        return page_of(file, parts, query)
    finally:
        close_parts(parts)
