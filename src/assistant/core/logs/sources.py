"""What the apps read as logs, by name: the files the daemon writes its records to (writer.py) and its
process output (output.py). Each one gives its latest entries matching a query, or follows them live."""

import asyncio
from collections.abc import AsyncGenerator, Iterable
from typing import Protocol

from assistant.core.logs.entries import LogEntry
from assistant.core.logs.files import LOG_FILES, LogFile, LogFileInfo, info
from assistant.core.logs.reader import LogPage, LogQuery, read_page
from assistant.core.logs.writer import LogWriter


class LogSource(Protocol):
    @property
    def name(self) -> str: ...

    def info(self) -> LogFileInfo:
        """Blocking: may stat a file."""
        ...

    async def page(self, query: LogQuery) -> LogPage: ...

    def follow(self, query: LogQuery) -> AsyncGenerator[LogPage | LogEntry]:
        """A page like `page`, then each new matching entry, until the caller stops reading."""
        ...


class WrittenLog:
    """One of the files the daemon writes its records to."""

    def __init__(self, writer: LogWriter, file: LogFile) -> None:
        self._writer = writer
        self._file = file

    @property
    def name(self) -> str:
        return self._file.name

    def info(self) -> LogFileInfo:
        return info(self._file)

    async def page(self, query: LogQuery) -> LogPage:
        return await read_page(self._file, query)

    def follow(self, query: LogQuery) -> AsyncGenerator[LogPage | LogEntry]:
        return self._writer.follow(self._file, query)


def log_sources(writer: LogWriter, *more: LogSource) -> dict[str, LogSource]:
    """The written files, then `more`, in the order the apps list them."""
    written: list[LogSource] = [WrittenLog(writer, f) for f in LOG_FILES.values()]
    return {s.name: s for s in [*written, *more]}


async def infos(sources: Iterable[LogSource]) -> list[LogFileInfo]:
    return await asyncio.to_thread(lambda: [s.info() for s in sources])
