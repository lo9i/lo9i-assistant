"""What git says changed in the handed folder, for the panel's Changed list and its marks in the tree."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from assistant.core.handed_folder import git, paths

# More than the panel can show usefully; the list says it was cut.
MAX_CHANGES = 500

ChangeKind = Literal["modified", "added", "deleted", "untracked"]


@dataclass(frozen=True)
class FileChange:
    # Relative to the handed folder; an untracked folder ends in "/", git listing it once for everything inside.
    path: str
    status: ChangeKind


@dataclass(frozen=True)
class FolderChanges:
    # Whether the folder is in a git repository; outside one nothing is listed.
    repository: bool
    changes: list[FileChange]
    # Only the first MAX_CHANGES are listed.
    truncated: bool = False


async def changes(root: Path) -> FolderChanges:
    where = await git.prefix(root)
    out = await git.status(root) if where is not None else None
    if where is None or out is None:
        return FolderChanges(repository=False, changes=[])
    # As the tree: an untracked node_modules isn't one of the changes.
    found = [c for c in parse_status(out, where) if not paths.always_hidden(c.path) and paths.sendable(c.path)]
    return FolderChanges(True, found[:MAX_CHANGES], len(found) > MAX_CHANGES)


def parse_status(out: bytes, prefix: str) -> list[FileChange]:
    """`git status --porcelain=v1 -z` read: its paths are the repository's, so only those under `prefix` (where the
    folder is in it) are kept, made relative to the folder. A rename is its new path added and its old one
    deleted; a conflict is a modification."""
    parts = [p.decode(errors="surrogateescape") for p in out.split(b"\0")]
    found: list[FileChange] = []
    at = 0
    while at < len(parts):
        entry = parts[at]
        at += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] in "RC":
            # Its old path is the next part.
            if code[0] == "R" and at < len(parts):
                found += _within(prefix, parts[at], "deleted")
            at += 1
        found += _within(prefix, path, _kind(code))
    return found


def _kind(code: str) -> ChangeKind | None:
    if code == "??":
        return "untracked"
    if code == "!!":
        return None
    if "U" in code or code in ("AA", "DD"):
        return "modified"
    if "D" in code:
        return "deleted"
    if code[0] in "ARC":
        return "added"
    return "modified"


def _within(prefix: str, path: str, kind: ChangeKind | None) -> list[FileChange]:
    if kind is None or not path.startswith(prefix):
        return []
    return [FileChange(path[len(prefix) :], kind)]
