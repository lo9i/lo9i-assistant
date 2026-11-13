"""Logs no one writes any more: the older parts the log files rotated into (`daemon.log.1`, core/logs/files.py), the
process output set aside at start (`output.log.1`, daemon/output.py), and the output LaunchDaemons installed before
the logs moved sent to the data home (`daemon.log` there, daemon/launchd.py::LEGACY_OUTPUT)."""

import re
from pathlib import Path

_ROTATED = re.compile(r".+\.log\.\d+")
_LEGACY_OUTPUT = "daemon.log"


def old_logs(logs: Path, home: Path) -> list[Path]:
    rotated = sorted(p for p in _files(logs) if _ROTATED.fullmatch(p.name))
    legacy = home / _LEGACY_OUTPUT
    # Where the logs folder is the home itself, that daemon.log is the live one.
    if logs != home and legacy.is_file() and not legacy.is_symlink():
        rotated.append(legacy)
    return rotated


def _files(folder: Path) -> list[Path]:
    try:
        return [p for p in folder.iterdir() if p.is_file() and not p.is_symlink()]
    except OSError:
        return []
