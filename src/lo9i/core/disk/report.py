"""How much disk lo9i takes, by category, and what cleaning would free. Blocking: it walks folders and reads
databases, so async code calls it in a thread."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from lo9i.core.disk import backups, database, orphans
from lo9i.core.disk.caches import caches
from lo9i.core.disk.logs import old_logs
from lo9i.core.disk.places import (
    BACKUPS,
    CATEGORIES,
    DATABASE,
    DOWNLOADS,
    LOGS,
    OTHER,
    PLUGIN_DATA,
    PLUGINS,
    UPLOADS,
    Places,
)
from lo9i.core.disk.sizes import Sizes

logger = logging.getLogger(__name__)

# Cleaned only when the user names them, never by cleaning everything: the files are the user's, outside lo9i's home.
ON_REQUEST = frozenset({DOWNLOADS})


@dataclass(frozen=True)
class CleanItem:
    category: str
    path: str
    # What removing it frees; for the database, its free pages and its log.
    bytes: int


@dataclass(frozen=True)
class DiskCategory:
    name: str
    bytes: int
    # What cleaning it frees.
    freeable: int
    # Cleaned only when named (ON_REQUEST).
    on_request: bool
    paths: list[str]


@dataclass(frozen=True)
class DiskReport:
    # The data home (~/.lo9i).
    home: str
    total: int
    # What cleaning every category but those cleaned on request frees.
    freeable: int
    categories: list[DiskCategory]
    # What cleaning removes, each category's.
    items: list[CleanItem]


@dataclass(frozen=True)
class Where:
    """What isn't a folder of `Places`: the database's files, the old copies, the downloads."""

    copies: list[Path]
    set_aside: list[Path]
    downloads: list[Path]
    download_folders: list[Path]


def build(places: Places, downloads: Sequence[Path], download_folders: Sequence[Path], now: float) -> DiskReport:
    """`downloads`: the plugins' finished downloads, in `download_folders`."""
    where = Where(
        backups.old_copies(places.home, places.database),
        backups.set_aside(places.home),
        list(downloads),
        list(download_folders),
    )
    sizes = measure(places, where)
    items = plan(places, where, now)
    return _report(places, where, sizes, items)


def measure(places: Places, where: Where) -> dict[str, int]:
    """Bytes per category. Each folder a category claims is measured without the others inside it, and the rest of the
    home is OTHER."""
    claimed = _claimed(places, where)
    sizes = Sizes()
    totals: dict[str, int] = dict.fromkeys(CATEGORIES, 0)
    for path, category in claimed.items():
        totals[category] += sizes.of(path, skip=claimed.keys() - {path})
    totals[DOWNLOADS] = sum(sizes.of(p) for p in where.downloads)
    totals[OTHER] += sizes.of(places.home, skip=claimed.keys())
    return totals


def _claimed(places: Places, where: Where) -> dict[Path, str]:
    claimed = places.roots() | {p: DATABASE for p in places.database_files()}
    return claimed | {p: BACKUPS for p in [*where.copies, *where.set_aside]}


def plan(places: Places, where: Where, now: float) -> list[CleanItem]:
    """What cleaning removes. Uploads are left out when lo9i's database can't be read."""
    sizes = Sizes()

    def items(category: str, paths: Sequence[Path]) -> list[CleanItem]:
        return [CleanItem(category, str(p), sizes.of(p)) for p in paths]

    found = items(LOGS, old_logs(places.logs, places.home)) + items(BACKUPS, where.copies)
    found += items(UPLOADS, _orphaned(places, now))
    found += items(PLUGINS, caches([places.plugins], now)) + items(PLUGIN_DATA, caches([places.plugin_data], now))
    found += items(DOWNLOADS, where.downloads)
    if space := database.free_space(places.database):
        found.append(CleanItem(DATABASE, str(places.database), space))
    return found


def _orphaned(places: Places, now: float) -> list[Path]:
    try:
        mentioned = orphans.mentioned_ids(places.database, places.plugin_data)
    except orphans.UnreadableDatabaseError as e:
        logger.warning("Couldn't read which uploads conversations refer to, so none is cleaned: %s", e)
        return []
    return orphans.orphaned(places.uploads, mentioned, now)


def _report(places: Places, where: Where, sizes: dict[str, int], items: list[CleanItem]) -> DiskReport:
    freeable = {name: sum(i.bytes for i in items if i.category == name) for name in CATEGORIES}
    paths = _paths(places, where)
    categories = [
        DiskCategory(name, sizes[name], freeable[name], name in ON_REQUEST, [str(p) for p in paths.get(name, [])])
        for name in CATEGORIES
    ]
    cleaned = sum(c.freeable for c in categories if not c.on_request)
    return DiskReport(str(places.home), sum(sizes.values()), cleaned, categories, items)


def _paths(places: Places, where: Where) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {}
    for path, category in _claimed(places, where).items():
        if path.exists():
            found.setdefault(category, []).append(path)
    return found | {DOWNLOADS: where.download_folders, OTHER: [places.home]}
