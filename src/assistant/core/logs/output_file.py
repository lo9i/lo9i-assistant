"""The daemon's output file (files.py::output_path): what a daemon started in the background (by the
terminal app or launchd) prints that isn't a log record. It's the daemon's own stdout and stderr, which
another process opened, so it's followed by watching for changes to it (FSEvents on macOS, inotify on
Linux) and reading what was added since. The folder is watched rather than the file, which may not
exist yet or be replaced."""

import asyncio
import logging
import os
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path

from watchfiles import Change, awatch

from assistant.core.logs.entries import LogEntry, parse_record
from assistant.core.logs.files import LogFileInfo
from assistant.core.logs.reader import LogPage, LogQuery

OUTPUT = "output"
OUTPUT_DESCRIPTION = (
    "What the daemon printed that isn't a log record: a crash before logging started, text a library printed."
)

# watchfiles logs every change it sees at INFO, which would add a record to the log for each line here.
logging.getLogger("watchfiles").setLevel(logging.WARNING)

# A page reads at most this much of the end of the file, which never rotates.
_TAIL_BYTES = 256 * 1024
# New lines show at most this long after they're written.
_DEBOUNCE_MS = 100


class OutputFile:
    name = OUTPUT

    def __init__(self, path: Path) -> None:
        self._path = path

    def info(self) -> LogFileInfo:
        size = self._path.stat().st_size if self._path.exists() else 0
        return LogFileInfo(self.name, self._path.name, OUTPUT_DESCRIPTION, str(self._path), size)

    async def page(self, query: LogQuery) -> LogPage:
        return await asyncio.to_thread(self._page, _Tail(self._path), query)

    async def follow(self, query: LogQuery) -> AsyncGenerator[LogPage | LogEntry]:
        tail = _Tail(self._path)
        await asyncio.to_thread(self._path.parent.mkdir, parents=True, exist_ok=True)
        stop = asyncio.Event()
        changes = awatch(
            self._path.parent,
            recursive=False,
            debounce=_DEBOUNCE_MS,
            step=20,
            watch_filter=self._is_this_file,
            stop_event=stop,
        )
        changed = asyncio.create_task(_next(changes))
        try:
            # Lets its first step start the watcher, which keeps every change from then on: whatever is
            # written after the page is read is seen.
            await asyncio.sleep(0)
            yield await asyncio.to_thread(self._page, tail, query)
            while await changed:
                for entry in await asyncio.to_thread(tail.added):
                    if query.matches(entry):
                        yield entry
                changed = asyncio.create_task(_next(changes))
        finally:
            # The watcher looks at `stop` between steps. Cancelled, it would wait for its thread, which
            # returns only on a change or after seconds.
            stop.set()
            await changed
            await changes.aclose()

    def _page(self, tail: "_Tail", query: LogQuery) -> LogPage:
        """Blocking."""
        entries = [e for e in tail.start() if query.matches(e)]
        return LogPage(self.info(), entries[-query.lines :])

    def _is_this_file(self, _change: Change, path: str) -> bool:
        return Path(path).name == self._path.name


async def _next(changes: AsyncIterator[set[tuple[Change, str]]]) -> bool:
    """Whether the file changed; False once the watcher stopped."""
    return await anext(changes, None) is not None


class _Tail:
    """How far the file was read: up to `_position` of the file with `_inode`, and the start of a line
    that wasn't finished then."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._inode: int | None = None
        self._position = 0
        self._partial = b""

    def start(self) -> list[LogEntry]:
        """Blocking. The lines at the end of the file; reading goes on after them."""
        try:
            stream = self._path.open("rb")
        except FileNotFoundError:
            return []
        with stream:
            stat = os.fstat(stream.fileno())
            begin = max(0, stat.st_size - _TAIL_BYTES)
            stream.seek(begin)
            data = stream.read(stat.st_size - begin)
        self._inode, self._position = stat.st_ino, begin + len(data)
        # Reading from the middle of the file starts in the middle of a line.
        return self._lines(data.partition(b"\n")[2] if begin else data)

    def added(self) -> list[LogEntry]:
        """Blocking. The lines finished since the last read. A file replaced or cut short is read
        again from its start."""
        try:
            stream = self._path.open("rb")
        except FileNotFoundError:
            return []
        with stream:
            stat = os.fstat(stream.fileno())
            if stat.st_ino != self._inode or stat.st_size < self._position:
                self._inode, self._position, self._partial = stat.st_ino, 0, b""
            stream.seek(self._position)
            data = stream.read()
        self._position += len(data)
        return self._lines(self._partial + data)

    def _lines(self, data: bytes) -> list[LogEntry]:
        """Each finished line as an entry; the unfinished one is kept for the next read."""
        finished, newline, self._partial = data.rpartition(b"\n")
        if not newline:
            return []
        return [parse_record(line.decode(errors="replace").rstrip("\r")) for line in finished.split(b"\n")]
