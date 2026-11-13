"""The disk lo9i takes, by category, and cleaning what can go without losing anything (core/disk/)."""

import asyncio
import time
from collections.abc import Collection
from dataclasses import dataclass

from lo9i.core import disk
from lo9i.core.agent.base import ServiceBase
from lo9i.core.disk import CATEGORIES, ON_REQUEST, CleanFailure, CleanItem, DiskCategory, DiskReport
from lo9i.core.disk.places import DATABASE
from lo9i.core.i18n import said
from lo9i.core.mcp import downloads

__all__ = [
    "CleanFailure",
    "CleanItem",
    "CleanReport",
    "DiskCategory",
    "DiskMixin",
    "DiskReport",
    "UnknownCategoryError",
]


class UnknownCategoryError(Exception):
    """A category to clean that isn't one."""


@dataclass(frozen=True)
class CleanReport:
    freed: int
    removed: list[CleanItem]
    failed: list[CleanFailure]
    # The disk use after it.
    usage: DiskReport


class DiskMixin(ServiceBase):
    async def disk_usage(self) -> DiskReport:
        folders = await downloads.every(self._storage.store, self.secrets)
        return await asyncio.to_thread(_report, folders)

    async def clean_disk(self, categories: Collection[str] = ()) -> CleanReport:
        """Cleans `categories`, or every one but those cleaned only on request when it's empty. The database is
        compacted only while no run is in progress, whose writes would wait for it. Raises UnknownCategoryError."""
        chosen = _chosen(categories)
        items = [i for i in (await self.disk_usage()).items if i.category in chosen]
        waiting = [i for i in items if i.category == DATABASE and self._open_runs]
        cleaned = await asyncio.to_thread(disk.clean, disk.from_settings(), [i for i in items if i not in waiting])
        failed = [*cleaned.failed, *(CleanFailure(i.path, _RUNS_IN_PROGRESS) for i in waiting)]
        return CleanReport(cleaned.freed, cleaned.removed, failed, await self.disk_usage())


_RUNS_IN_PROGRESS = said("Replies are running, so the database wasn't compacted: clean it again once they end.")


def _chosen(categories: Collection[str]) -> set[str]:
    if unknown := set(categories) - set(CATEGORIES):
        raise UnknownCategoryError(said("There's no category {names} to clean.", names=", ".join(sorted(unknown))))
    return set(categories) or {c for c in CATEGORIES if c not in ON_REQUEST}


def _report(folders: list[downloads.DownloadsFolder]) -> DiskReport:
    files = [path for folder in folders for path in folder.finished()]
    return disk.build(disk.from_settings(), files, [f.folder for f in folders], time.time())
