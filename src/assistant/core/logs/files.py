"""The daemon's log files under LOGS_DIR. The daemon writes them itself (writer.py), however it was
started (from the terminal app, at boot by launchd or systemd, or in the foreground), so the apps can
read them the same way everywhere. Each one rotates: at `max_bytes` it becomes `<name>.log.1`, and
the oldest of `backups` goes."""

import logging
from dataclasses import dataclass
from pathlib import Path

from assistant.core.config import settings


@dataclass(frozen=True)
class LogFile:
    name: str
    description: str
    # The lowest level it keeps.
    level: int
    max_bytes: int
    backups: int

    @property
    def file_name(self) -> str:
        return f"{self.name}.log"

    def path(self) -> Path:
        return logs_dir() / self.file_name

    def paths(self) -> list[Path]:
        """The current file, then its older parts, newest first."""
        return [self.path(), *(self.path().with_name(f"{self.file_name}.{n}") for n in range(1, self.backups + 1))]


@dataclass
class LogFileInfo:
    name: str
    file_name: str
    description: str
    # Where it is: a file's path, or the command that reads it (the journal).
    path: str
    # Of the current file; 0 when nothing was written yet, None when it isn't a file (the journal).
    size: int | None


_MB = 1024 * 1024

LOG_FILES: dict[str, LogFile] = {
    f.name: f
    for f in (
        LogFile("daemon", "Everything the daemon logs.", logging.NOTSET, 5 * _MB, 3),
        # Errors are rare, so this keeps them long after the busy daemon log has rotated them away.
        LogFile("errors", "Only errors, kept for longer.", logging.ERROR, 1 * _MB, 3),
    )
}


def logs_dir() -> Path:
    return Path(settings.logs_dir).expanduser()


def output_path() -> Path:
    """Where a daemon started in the background writes what isn't a log record: a crash before
    logging starts, or text a library prints. Under systemd it goes to the journal instead."""
    return logs_dir() / "output.log"


def info(file: LogFile) -> LogFileInfo:
    """Blocking: stats the file."""
    path = file.path()
    size = path.stat().st_size if path.exists() else 0
    return LogFileInfo(file.name, file.file_name, file.description, str(path), size)
