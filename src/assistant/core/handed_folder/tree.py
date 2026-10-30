"""The handed folder's tree as the panel shows it: what's on disk (contents.py), with what git says was deleted
there (changes.py) where it was, so a deleted file shows in the tree and not only in the Changed list, and so does a
folder deleted with everything in it, which opens on those files. A refresh reads every open folder and the changes
together, asking git once: `git status` takes a while in a big repository."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from assistant.core.handed_folder import changes, contents, paths
from assistant.core.handed_folder.changes import FolderChanges
from assistant.core.handed_folder.contents import FolderContents, FolderEntry
from assistant.core.handed_folder.paths import HandedFolderError, MissingPathError


@dataclass(frozen=True)
class ListedFolder:
    """A folder of the tree as `listed` reads it, or why it couldn't be (gone since, outside the folder)."""

    path: str
    contents: FolderContents | None = None
    error: str = ""


@dataclass(frozen=True)
class FolderRefresh:
    """The open folders of the tree and what git says changed, read together."""

    folders: list[ListedFolder]
    changes: FolderChanges


async def listed(root: Path, path: str) -> FolderContents:
    """The files and folders in `path`, the deleted ones among them. Raises as contents.contents, but for a folder
    gone with what git says was deleted in it."""
    return await _listed(root, path, await changes.changes(root))


async def refreshed(root: Path, folders: list[str]) -> FolderRefresh:
    """Each of `folders` as `listed` reads it, and the changes, git asked once. Raises MissingPathError when the
    handed folder itself is gone."""
    found = await changes.changes(root)
    listings = await asyncio.gather(*(_listing(root, path, found) for path in dict.fromkeys(folders)))
    return FolderRefresh(list(listings), found)


async def _listing(root: Path, path: str, found: FolderChanges) -> ListedFolder:
    try:
        return ListedFolder(path, await _listed(root, path, found))
    except HandedFolderError as e:
        return ListedFolder(path, error=str(e))


async def _listed(root: Path, path: str, found: FolderChanges) -> FolderContents:
    where = paths.normal(path)
    gone = [c.path for c in found.changes if c.status == "deleted"]
    try:
        on_disk = await contents.contents(root, where)
    except MissingPathError:
        if not _below(gone, where):
            raise
        on_disk = FolderContents(where, [])
    return _with_gone(on_disk, _below(gone, where))


def _below(gone: list[str], where: str) -> list[str]:
    """The deleted paths inside `where`, relative to it."""
    prefix = f"{where}/" if where else ""
    return [path[len(prefix) :] for path in gone if path.startswith(prefix)]


def _with_gone(on_disk: FolderContents, gone: list[str]) -> FolderContents:
    """The entries on disk, then one per deleted file or folder directly in it that isn't there now, sorted as the
    tree is: folders first, then files, by name."""
    names = {e.name for e in on_disk.entries}
    added: dict[str, FolderEntry] = {}
    for relative in gone:
        name, _, rest = relative.partition("/")
        if name not in names and name not in added:
            path = f"{on_disk.path}/{name}" if on_disk.path else name
            added[name] = FolderEntry(name, path, folder=bool(rest), size=0, deleted=True)
    entries = sorted([*on_disk.entries, *added.values()], key=lambda e: (not e.folder, e.name.lower()))
    return FolderContents(on_disk.path, entries, on_disk.truncated)
