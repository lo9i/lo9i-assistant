"""Keeping what lo9i writes bounded without the user: the daemon runs `Housekeeping` as a supervised task, at start and
once a day after. It cleans, through the same `disk.clean` as `lo9i clean` and the Disk use card:

- the coding agents' tasks that ended over 30 days ago (core/agent_tasks/pruning.py);
- uploads nothing refers to, older than UPLOADS_KEEP_DAYS (core/disk/orphans.py: a file any message, record or
  plugin's database names is kept, however old);
- tool outputs in the search index from turns older than OUTPUTS_KEEP_DAYS (what was said stays searchable, and the
  checkpoints keep the outputs whole);
- the database's free space, rebuilt (VACUUM) only once it's worth it (COMPACT_SHARE of the file and at least
  COMPACT_BYTES) and no run is in progress, since its writes would wait for it.

Checkpoints need nothing here: each conversation keeps only its latest already (core/checkpoints.py), which holds its
history. What only `lo9i clean` removes (old copies, rotated logs, caches, empty databases) stays the user's call."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from lo9i.core import disk
from lo9i.core.agent_tasks import pruning
from lo9i.core.conversation.search import MessageIndex
from lo9i.core.disk import database
from lo9i.core.disk.places import DATABASE, UPLOADS
from lo9i.core.disk.report import orphaned_uploads
from lo9i.core.disk.sizes import Sizes

logger = logging.getLogger(__name__)

OUTPUTS_KEEP_DAYS = 90
UPLOADS_KEEP_DAYS = 90
COMPACT_SHARE = 0.2
COMPACT_BYTES = 32 * 1024 * 1024
EVERY_SECONDS = 24 * 3600
# Ticks read the wall clock, so a computer waking from sleep catches up within one.
_TICK_SECONDS = 3600
_DAY = 24 * 3600


def outputs_before(now: float) -> str:
    """The local day tool outputs from before it are forgotten, as the index writes a turn's time ("2026-08-18")."""
    return (datetime.fromtimestamp(now).astimezone() - timedelta(days=OUTPUTS_KEEP_DAYS)).strftime("%Y-%m-%d")


@dataclass(frozen=True)
class Tidied:
    forgotten_outputs: int
    cleaned: disk.Cleaned


def plan(roots: list[Path], places: disk.Places, now: float, may_compact: bool) -> list[disk.CleanItem]:
    """What housekeeping removes. Blocking."""
    sizes = Sizes()
    uploads = orphaned_uploads(places, now, UPLOADS_KEEP_DAYS * _DAY)
    found = pruning.items(roots, now) + [disk.CleanItem(UPLOADS, str(p), sizes.of(p)) for p in uploads]
    if may_compact and worth_compacting(places.database):
        found.append(disk.CleanItem(DATABASE, str(places.database), database.free_space(places.database)))
    return found


def worth_compacting(path: Path) -> bool:
    free = database.free_space(path)
    return free >= COMPACT_BYTES and free >= COMPACT_SHARE * database.files_size(path)


class Housekeeping:
    """`roots` gives the installed agents' task folders; `runs` how many runs are in progress."""

    name = "housekeeping"

    def __init__(self, roots: Callable[[], list[Path]], search: MessageIndex, runs: Callable[[], int]) -> None:
        self._roots = roots
        self._search = search
        self._runs = runs
        self._done_at: float | None = None

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.tick(time.time())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=_TICK_SECONDS)

    async def tick(self, now: float) -> None:
        if self._done_at is not None and now - self._done_at < EVERY_SECONDS:
            return
        self._done_at = now
        _log(await self.tidy(now))

    async def tidy(self, now: float) -> Tidied:
        forgotten = await self._search.forget_tool_outputs(outputs_before(now))
        places = disk.from_settings()
        items = await asyncio.to_thread(plan, self._roots(), places, now, not self._runs())
        return Tidied(forgotten, await asyncio.to_thread(disk.clean, places, items))


def _log(tidied: Tidied) -> None:
    cleaned = tidied.cleaned
    if not (tidied.forgotten_outputs or cleaned.removed or cleaned.failed):
        return
    by_category: dict[str, int] = {}
    for item in cleaned.removed:
        by_category[item.category] = by_category.get(item.category, 0) + 1
    logger.info(
        "Housekeeping freed %d bytes: removed %s, forgot %d old tool outputs; %d couldn't be removed",
        cleaned.freed,
        ", ".join(f"{n} {category}" for category, n in sorted(by_category.items())) or "nothing",
        tidied.forgotten_outputs,
        len(cleaned.failed),
    )
    for failure in cleaned.failed:
        logger.warning("Housekeeping couldn't remove %s: %s", failure.path, failure.reason)
