"""Old tasks' folders (records.py), which nothing reads once their task ended long ago: those whose task ended (its
result written, its worker gone) and that haven't changed in KEEP_DAYS. Never one still running. The disk plan
(core/disk/report.py) cleans them with the rest, and the daemon's housekeeping (core/housekeeping.py) on its own, both
through `disk.clean`, so they remove the same folders.

The conversations and panels that name a pruned task already take a task that isn't there (`AgentTaskError`)."""

import contextlib
import os
import subprocess
from collections.abc import Iterable
from pathlib import Path

from lo9i.core import disk
from lo9i.core.disk.places import PLUGIN_DATA
from lo9i.core.disk.sizes import Sizes

KEEP_DAYS = 30
_RESULT = "result.json"


def old_ended(roots: Iterable[Path], now: float) -> list[Path]:
    """The task folders under each of `roots` whose task ended and that last changed over KEEP_DAYS before `now`."""
    cutoff = now - KEEP_DAYS * 24 * 3600
    old = [f for root in roots if root.is_dir() for f in sorted(root.iterdir()) if _ended_before(f, cutoff)]
    if not old:
        return []
    running = _running_commands()
    return [folder for folder in old if str(folder) not in running]


def _ended_before(folder: Path, cutoff: float) -> bool:
    return (
        folder.is_dir() and not folder.is_symlink() and (folder / _RESULT).is_file() and _last_change(folder) < cutoff
    )


def _last_change(folder: Path) -> float:
    latest = folder.lstat().st_mtime
    for here, _, files in os.walk(folder):
        for name in files:
            with contextlib.suppress(OSError):
                latest = max(latest, (Path(here) / name).lstat().st_mtime)
    return latest


def _running_commands() -> str:
    """Every process's command line: a worker's names its task's folder (records.py::TaskStore._alive)."""
    found = subprocess.run(["ps", "-axo", "command="], capture_output=True, text=True, check=True)
    return found.stdout


def items(roots: Iterable[Path], now: float) -> list[disk.CleanItem]:
    """The old ended tasks' folders as items for `disk.clean`. Blocking."""
    sizes = Sizes()
    return [disk.CleanItem(PLUGIN_DATA, str(p), sizes.of(p)) for p in old_ended(roots, now)]
