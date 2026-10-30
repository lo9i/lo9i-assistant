"""The handed folder's tree as the panel shows it: what's on disk (contents.py), with what git says was deleted
there (changes.py) where it was, so a deleted file shows in the tree and not only in the Changed list, and so does a
folder deleted with everything in it, which opens on those files."""

from pathlib import Path

from assistant.core.handed_folder import changes, contents, paths
from assistant.core.handed_folder.contents import FolderContents, FolderEntry
from assistant.core.handed_folder.paths import MissingPathError


async def listed(root: Path, path: str) -> FolderContents:
    """The files and folders in `path`, the deleted ones among them. Raises as contents.contents, but for a folder
    gone with what git says was deleted in it."""
    where = paths.normal(path)
    found = await changes.changes(root)
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
