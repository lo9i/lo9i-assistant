"""Writing the daemon's log records to its log files (files.py), and handing each new one to the
readers following a file live. Writing and handing over happen under the handler's lock, and a
reader starts following under it too, so what it read before (reader.py) and what it is handed
after meet exactly."""

import asyncio
import logging
import sys
from collections.abc import AsyncGenerator, Iterable
from logging.handlers import RotatingFileHandler

from assistant.core.logs.entries import FORMAT, LogEntry, parse_record
from assistant.core.logs.files import LOG_FILES, LogFile, logs_dir
from assistant.core.logs.reader import LogPage, LogQuery, OpenPart, close_parts, open_parts, page_of


class _Follower:
    """A reader of one file: new entries the file keeps go into its queue, on its event loop."""

    def __init__(self, file: LogFile, loop: asyncio.AbstractEventLoop) -> None:
        self.file = file
        self.queue: asyncio.Queue[LogEntry] = asyncio.Queue()
        self._loop = loop

    def offer(self, entry: LogEntry, levelno: int) -> None:
        if levelno >= self.file.level:
            self._loop.call_soon_threadsafe(self.queue.put_nowait, entry)


class LogWriter(logging.Handler):
    """The root logger's handler in the daemon: one rotating file handler per log file, each taking
    the records at its level or above, and the followers."""

    def __init__(self, files: Iterable[LogFile] = LOG_FILES.values()) -> None:
        super().__init__()
        self.setFormatter(logging.Formatter(FORMAT))
        logs_dir().mkdir(parents=True, exist_ok=True)
        self._files = {f.name: (f, self._rotating(f)) for f in files}
        self._followers: set[_Follower] = set()

    def emit(self, record: logging.LogRecord) -> None:
        for file, handler in self._files.values():
            if record.levelno >= file.level:
                handler.handle(record)
        if self._followers:
            entry = parse_record(self.format(record))
            for follower in self._followers:
                follower.offer(entry, record.levelno)

    def close(self) -> None:
        for _, handler in self._files.values():
            handler.close()
        super().close()

    async def follow(self, file: LogFile, query: LogQuery) -> AsyncGenerator[LogPage | LogEntry]:
        """The latest entries matching `query`, then each new one, until the caller stops reading."""
        follower = _Follower(file, asyncio.get_running_loop())
        parts = await asyncio.to_thread(self._start, follower)
        try:
            try:
                page = await asyncio.to_thread(page_of, file, parts, query)
            finally:
                close_parts(parts)
            yield page
            while True:
                if query.matches(entry := await follower.queue.get()):
                    yield entry
        finally:
            self._stop(follower)

    def _start(self, follower: _Follower) -> list[OpenPart]:
        """Blocking: opens the file's parts and starts handing new entries over, with no record in between."""
        self.acquire()
        try:
            self._followers.add(follower)
            return open_parts(follower.file)
        finally:
            self.release()

    def _stop(self, follower: _Follower) -> None:
        self.acquire()
        try:
            self._followers.discard(follower)
        finally:
            self.release()

    def _rotating(self, file: LogFile) -> RotatingFileHandler:
        # Delayed, so a file is created with its first record.
        handler = RotatingFileHandler(
            file.path(), maxBytes=file.max_bytes, backupCount=file.backups, encoding="utf-8", delay=True
        )
        handler.setFormatter(self.formatter)
        return handler


def configure(writer: LogWriter, level: int = logging.INFO) -> None:
    """The daemon's logging: every record goes to the log files. In a terminal (`assistant daemon`)
    records show there too; started in the background, its output is only what isn't a record."""
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(writer)
    if sys.stderr.isatty():
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(console)
