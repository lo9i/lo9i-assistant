"""The handed folder's tree, one folder at a time as the panel opens it: folders first, then files, by name, without
what the panel never shows (paths.ALWAYS_HIDDEN, what git ignores, links that lead outside the folder)."""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from assistant.core.handed_folder import git, paths
from assistant.core.handed_folder.paths import HandedFolderError, MissingPathError

# A folder with more inside lists the first ones and says it was cut.
MAX_ENTRIES = 1000


@dataclass(frozen=True)
class FolderEntry:
    name: str
    # Relative to the handed folder.
    path: str
    folder: bool
    # In bytes; 0 for a folder.
    size: int


@dataclass(frozen=True)
class FolderContents:
    # Relative to the handed folder; "" for the folder itself.
    path: str
    entries: list[FolderEntry]
    # Only the first MAX_ENTRIES are listed.
    truncated: bool = False


async def contents(root: Path, path: str) -> FolderContents:
    """Raises OutsideFolderError for a path outside `root` or one the panel doesn't show, MissingPathError for one
    that isn't a folder there, HandedFolderError for one that can't be read."""
    where = paths.normal(path)
    target = await paths.shown(root, where)
    found = await asyncio.to_thread(_entries, root, target, where)
    hidden = await git.ignored(root, [e.path for e in found])
    kept = [e for e in found if e.path not in hidden]
    return FolderContents(where, kept[:MAX_ENTRIES], len(kept) > MAX_ENTRIES)


def _entries(root: Path, target: Path, path: str) -> list[FolderEntry]:
    if not target.is_dir():
        raise MissingPathError(f"{path or '.'} isn't a folder.")
    try:
        with os.scandir(target) as found:
            entries = [e for e in (_entry(root, path, item) for item in found) if e is not None]
    except OSError as e:
        raise HandedFolderError(f"Can't read {path or '.'}: {e.strerror or e}") from e
    return sorted(entries, key=lambda e: (not e.folder, e.name.lower()))


def _entry(root: Path, path: str, item: os.DirEntry[str]) -> FolderEntry | None:
    """None for what the tree leaves out, or a name that isn't text the apps can be sent."""
    if item.name in paths.ALWAYS_HIDDEN or not paths.sendable(item.name):
        return None
    try:
        if item.is_symlink() and not Path(item.path).resolve().is_relative_to(root):
            return None
        folder = item.is_dir()
        size = 0 if folder else item.stat().st_size
    except OSError:
        return None
    return FolderEntry(item.name, f"{path}/{item.name}" if path else item.name, folder, size)
