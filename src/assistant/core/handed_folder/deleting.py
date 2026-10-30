"""Deleting a file of the folder the panel shows, when the user asks from it: only a file the tree shows
(paths.shown), never a folder. It goes to the system's trash (trash.py), where the user can take it back. A link goes
there itself, not what it leads to."""

import asyncio
from pathlib import Path

from assistant.core.handed_folder import paths, trash
from assistant.core.handed_folder.paths import HandedFolderError, MissingPathError


async def delete(root: Path, path: str) -> None:
    """Raises OutsideFolderError for a path outside `root` or one the panel doesn't show, MissingPathError for one
    that isn't a file there, HandedFolderError for one that can't be moved to the trash."""
    where = paths.normal(path)
    target = await paths.shown(root, where)
    await asyncio.to_thread(_to_trash, root / where, target, where)


def _to_trash(entry: Path, target: Path, path: str) -> None:
    if target.is_dir():
        raise MissingPathError(f"{path or '.'} isn't a file.")
    try:
        trash.move(entry)
    except OSError as e:
        raise HandedFolderError(f"Can't move {path} to the trash: {e.strerror or e}") from e
