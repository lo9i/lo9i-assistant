"""Removing what the report's plan says cleaning removes. Blocking, like the report."""

import shutil
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from lo9i.core.disk import database
from lo9i.core.disk.places import DATABASE, UPLOADS, Places
from lo9i.core.disk.report import CleanItem


@dataclass(frozen=True)
class CleanFailure:
    path: str
    reason: str


@dataclass(frozen=True)
class Cleaned:
    freed: int
    removed: list[CleanItem]
    failed: list[CleanFailure]


def clean(places: Places, items: Sequence[CleanItem]) -> Cleaned:
    freed, removed, failed = 0, [], []
    for item in items:
        try:
            freed += _clean(places, item)
        except (OSError, sqlite3.Error) as e:
            failed.append(CleanFailure(item.path, str(e)))
            continue
        removed.append(item)
    return Cleaned(freed, removed, failed)


def _clean(places: Places, item: CleanItem) -> int:
    """What it freed."""
    path = Path(item.path)
    if item.category == DATABASE:
        before = database.files_size(path)
        database.compact(path)
        return max(before - database.files_size(path), 0)
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
    if item.category == UPLOADS:
        _remove_empty_folder(path.parent, places.uploads)
    return item.bytes


def _remove_empty_folder(folder: Path, uploads: Path) -> None:
    """The folder core/uploads.py made for the file, once nothing else is in it."""
    if folder != uploads and folder.is_relative_to(uploads) and not any(folder.iterdir()):
        folder.rmdir()
