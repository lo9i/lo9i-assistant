"""Old tasks' folders (records.py), which nothing reads once their task ended long ago: those whose task ended (its
result written, its worker gone) and that haven't changed in KEEP_DAYS. Never one still running. The disk plan
(core/disk/report.py) cleans them with the rest, and `TaskPruning`, a supervised daemon task, cleans them on its own at
start and once a day after, both through `disk.clean`, so they remove the same folders.

The conversations and panels that name a pruned task already take a task that isn't there (`AgentTaskError`)."""

import asyncio
import contextlib
import logging
import os
import subprocess
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from lo9i.core import disk
from lo9i.core.disk.places import PLUGIN_DATA
from lo9i.core.disk.sizes import Sizes

logger = logging.getLogger(__name__)

KEEP_DAYS = 30
EVERY_SECONDS = 24 * 3600
# Ticks read the wall clock, so a computer waking from sleep catches up within one.
_TICK_SECONDS = 3600
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


def prune(roots: Iterable[Path], places: disk.Places, now: float) -> disk.Cleaned:
    """Removes the old ended tasks' folders as cleaning the disk does. Blocking."""
    sizes = Sizes()
    items = [disk.CleanItem(PLUGIN_DATA, str(p), sizes.of(p)) for p in old_ended(roots, now)]
    return disk.clean(places, items)


class TaskPruning:
    """Prunes the coding agents' old tasks at start and every EVERY_SECONDS after. `roots` gives the installed agents'
    task folders."""

    name = "task pruning"

    def __init__(self, roots: Callable[[], list[Path]]) -> None:
        self._roots = roots
        self._pruned_at: float | None = None

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.tick(time.time())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=_TICK_SECONDS)

    async def tick(self, now: float) -> None:
        if self._pruned_at is not None and now - self._pruned_at < EVERY_SECONDS:
            return
        self._pruned_at = now
        cleaned = await asyncio.to_thread(prune, self._roots(), disk.from_settings(), now)
        if cleaned.removed or cleaned.failed:
            logger.info(
                "Pruned %d old coding tasks, freeing %d bytes; %d couldn't be removed",
                len(cleaned.removed),
                cleaned.freed,
                len(cleaned.failed),
            )
