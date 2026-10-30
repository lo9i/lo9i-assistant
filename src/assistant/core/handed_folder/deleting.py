"""Deleting a file of the folder the panel shows, when the user asks from it: only a file the tree shows
(paths.shown), never a folder. A link is deleted itself, not what it leads to."""

import asyncio
from pathlib import Path

from assistant.core.handed_folder import paths
from assistant.core.handed_folder.paths import HandedFolderError, MissingPathError


async def delete(root: Path, path: str) -> None:
    """Raises OutsideFolderError for a path outside `root` or one the panel doesn't show, MissingPathError for one
    that isn't a file there, HandedFolderError for one that can't be deleted."""
    where = paths.normal(path)
    target = await paths.shown(root, where)
    await asyncio.to_thread(_unlink, root / where, target, where)


def _unlink(entry: Path, target: Path, path: str) -> None:
    if target.is_dir():
        raise MissingPathError(f"{path or '.'} isn't a file.")
    try:
        entry.unlink()
    except OSError as e:
        raise HandedFolderError(f"Can't delete {path}: {e.strerror or e}") from e
