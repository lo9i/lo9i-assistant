"""The daemon's own stdout and stderr when they go to a file: output.log, where launchd and the terminal app send
them (core/logs/files.py::output_path), and what isn't a log record ends up (a crash before logging starts, text
a library prints). The file was opened by whatever started the daemon, so only the daemon can move off it.

At start, an output.log past `LIMIT` is kept as output.log.1, replacing the one before, and the daemon writes to
a new output.log, so the file never grows for as long as it's used. Under systemd the output goes to the journal,
which rotates itself, and in a terminal it goes to the terminal: neither is touched."""

import os
import sys
from pathlib import Path

LIMIT = 10 * 1024 * 1024


def rotate(path: Path, limit: int = LIMIT) -> bool:
    """Keeps a full output file as the one before, when it's where the daemon writes. Returns whether it did."""
    if not is_stderr(path) or path.stat().st_size <= limit:
        return False
    os.replace(path, kept(path))
    send_output_to(path)
    return True


def kept(path: Path) -> Path:
    """Where the output before the last rotation is: output.log.1."""
    return path.with_name(path.name + ".1")


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
