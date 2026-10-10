"""The daemon's output under systemd: the journal of its service, read with `journalctl` and followed
with `journalctl --follow`, which is told of new entries by the journal (inotify). Entries are read as
JSON, so each keeps its time, priority and the program that wrote it: the daemon, or systemd saying
the service stopped or started."""

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, Sequence
from datetime import datetime
from typing import Any

from assistant.core.logs.components import OTHER
from assistant.core.logs.entries import LogEntry
from assistant.core.logs.files import LogFileInfo
from assistant.core.logs.output_file import OUTPUT, OUTPUT_DESCRIPTION
from assistant.core.logs.reader import MAX_LINES, LogPage, LogQuery

# syslog priorities, as levels.
_LEVELS = {"0": "CRITICAL", "1": "CRITICAL", "2": "CRITICAL", "3": "ERROR", "4": "WARNING", "7": "DEBUG"}
_STOP_SECONDS = 5


class JournalError(Exception):
    """journalctl isn't there or refused."""


class Journal:
    name = OUTPUT

    def __init__(self, unit: str, command: Sequence[str] = ("journalctl",)) -> None:
        self._command = [*command, f"--user-unit={unit}", "--output=json", "--no-pager", "--quiet"]

    def info(self) -> LogFileInfo:
        return LogFileInfo(self.name, "journal", OUTPUT_DESCRIPTION, " ".join(self._command[:2]), None)

    async def page(self, query: LogQuery) -> LogPage:
        return LogPage(self.info(), (await self._latest(query))[0])

    async def follow(self, query: LogQuery) -> AsyncGenerator[LogPage | LogEntry]:
        """After the page, the entries after the last one it read, so none is missed or repeated."""
        entries, cursor = await self._latest(query)
        yield LogPage(self.info(), entries)
        if cursor is None:
            # The page says why the journal can't be read; there's nothing to follow.
            await asyncio.Event().wait()
        after = f"--after-cursor={cursor}" if cursor else "--lines=all"
        # Its errors aren't read while it runs, so they mustn't fill a pipe.
        proc = await self._start("--follow", after, errors=asyncio.subprocess.DEVNULL)
        try:
            assert proc.stdout is not None
            async for line in proc.stdout:
                if query.matches(entry := _entry(json.loads(line))):
                    yield entry
        finally:
            await _stop(proc)

    async def _latest(self, query: LogQuery) -> tuple[list[LogEntry], str | None]:
        """The latest entries matching `query`, and the cursor of the last entry read: "" when there's
        none, None when the journal couldn't be read (the one entry says why)."""
        try:
            output = await self._read(f"--lines={MAX_LINES}")
        except JournalError as e:
            return [_failed(str(e))], None
        fields = [json.loads(line) for line in output.splitlines() if line.strip()]
        matching = [e for e in map(_entry, fields) if query.matches(e)]
        return matching[-query.lines :], fields[-1]["__CURSOR"] if fields else ""

    async def _read(self, *args: str) -> bytes:
        proc = await self._start(*args)
        output, errors = await proc.communicate()
        if proc.returncode != 0:
            raise JournalError(f"journalctl failed: {errors.decode(errors='replace').strip()}")
        return output

    async def _start(self, *args: str, errors: int = asyncio.subprocess.PIPE) -> asyncio.subprocess.Process:
        try:
            return await asyncio.create_subprocess_exec(
                *self._command, *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=errors
            )
        except FileNotFoundError as e:
            raise JournalError(f"{self._command[0]} isn't installed, so the journal can't be read.") from e


def _entry(fields: dict[str, Any]) -> LogEntry:
    time = datetime.fromtimestamp(int(fields["__REALTIME_TIMESTAMP"]) / 1_000_000)
    level = _LEVELS.get(str(fields.get("PRIORITY", "")), "INFO")
    return LogEntry(_stamp(time), level, fields.get("SYSLOG_IDENTIFIER", ""), OTHER, _text(fields.get("MESSAGE")))


def _failed(message: str) -> LogEntry:
    return LogEntry(_stamp(datetime.now()), "ERROR", "journalctl", OTHER, message)


def _stamp(time: datetime) -> str:
    """As log records are stamped (entries.py::FORMAT)."""
    return time.strftime("%Y-%m-%d %H:%M:%S") + f",{time.microsecond // 1000:03d}"


def _text(message: Any) -> str:
    """The journal gives a message that isn't valid UTF-8 as a list of bytes."""
    if isinstance(message, list):
        return bytes(message).decode(errors="replace")
    return message if isinstance(message, str) else ""


async def _stop(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), _STOP_SECONDS)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
