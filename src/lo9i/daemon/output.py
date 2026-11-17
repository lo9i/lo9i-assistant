"""The daemon's own stdout and stderr when they go to a file: output.log, where launchd and the terminal app send
them (core/logs/files.py::output_path), and what isn't a log record ends up (a crash before logging starts, text
a library prints). The file was opened by whatever started the daemon, so only the daemon can move off it.

At start, and every hour while the daemon runs (`OutputRotation`, a supervised task), an output.log past `LIMIT` is
kept as output.log.1, the older parts moving up to output.log.`BACKUPS` and the oldest going, and the daemon writes to
a new output.log, as the log files rotate (core/logs/files.py), so the file never grows past it for long. Under
systemd the output goes to the journal, which rotates itself, and in a terminal it goes to the terminal: neither is
touched."""

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

LIMIT = 5 * 1024 * 1024
BACKUPS = 3
_CHECK_SECONDS = 3600


def rotate(path: Path, limit: int = LIMIT) -> bool:
    """Keeps a full output file as the one before, when it's where the daemon writes. Returns whether it did."""
    if not is_stderr(path) or path.stat().st_size <= limit:
        return False
    for n in range(BACKUPS - 1, 0, -1):
        with contextlib.suppress(FileNotFoundError):
            os.replace(_part(path, n), _part(path, n + 1))
    os.replace(path, _part(path, 1))
    send_output_to(path)
    return True


def kept(path: Path) -> Path:
    """Where the output before the last rotation is: output.log.1."""
    return _part(path, 1)


def _part(path: Path, n: int) -> Path:
    """An older part: output.log.1 is the one before the last rotation."""
    return path.with_name(f"{path.name}.{n}")


class OutputRotation:
    """Rotates the output file every hour, as `rotate` does at start."""

    name = "output rotation"

    def __init__(self, path: Path) -> None:
        self._path = path

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=_CHECK_SECONDS)
            if not stop.is_set() and await asyncio.to_thread(_rotated, self._path):
                logger.info("Rotated %s", self._path)


def _rotated(path: Path) -> bool:
    try:
        return rotate(path)
    except OSError as e:
        logger.warning("Couldn't rotate %s: %s", path, e)
        return False


def is_stderr(path: Path) -> bool:
    """Whether the daemon's stderr is this file."""
    try:
        stream, file = os.fstat(sys.stderr.fileno()), path.stat()
    except (OSError, ValueError):
        return False
    return (stream.st_dev, stream.st_ino) == (file.st_dev, file.st_ino)


def send_output_to(path: Path) -> None:
    """Points the daemon's stdout and stderr at the end of this file, created if it isn't there."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout.flush()
    sys.stderr.flush()
    output = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    os.dup2(output, sys.stdout.fileno())
    os.dup2(output, sys.stderr.fileno())
    os.close(output)
