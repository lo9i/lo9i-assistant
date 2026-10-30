"""Paths as the apps give them: relative to the folder the panel shows (the handed folder, or the home folder), with
`/` between parts, "" for the folder itself. Whatever would reach outside it is refused (an absolute path, a `..`, a
link whose target is elsewhere), and so is what the panel doesn't show (`shown`)."""

import asyncio
from pathlib import Path, PurePosixPath

from assistant.core.handed_folder import git

# Never shown, whatever git says: a repository's insides, and folders of installed packages too big to browse.
ALWAYS_HIDDEN = frozenset({".git", "node_modules", ".venv"})


class HandedFolderError(Exception):
    """A path that can't be read; its message says why."""


class OutsideFolderError(HandedFolderError):
    pass


class MissingPathError(HandedFolderError):
    pass


def root(folder: str) -> Path:
    """The folder, its links followed, so paths inside it are compared with where they really are."""
    where = Path(folder).resolve()
    if not where.is_dir():
        raise MissingPathError(f"{folder} isn't there any more.")
    return where


def normal(path: str) -> str:
    """`path` without empty parts or `.`: "src//app/" is "src/app"."""
    return "/".join(part for part in PurePosixPath(path).parts if part != ".")


def inside(root: Path, relative: str) -> Path:
    """`relative` in `root` (from `root()`), its links followed. Raises OutsideFolderError for a path that
    reaches outside it, MissingPathError for one that isn't there."""
    if "\0" in relative or relative.startswith("/") or ".." in PurePosixPath(relative).parts:
        raise OutsideFolderError(f"{relative} isn't inside the folder.")
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise OutsideFolderError(f"{relative} isn't inside the folder.")
    if not target.exists():
        raise MissingPathError(f"{relative} isn't there.")
    return target


async def shown(root: Path, relative: str) -> Path:
    """`relative` in `root`, as `inside` finds it, when the tree shows it: not through a folder it always hides,
    nor one git ignores, and neither is where a link there leads (a link to a .env). Raises OutsideFolderError
    otherwise, MissingPathError for a path that isn't there."""
    target = await asyncio.to_thread(inside, root, relative)
    for path in {relative, target.relative_to(root).as_posix()} - {"", "."}:
        if always_hidden(path) or await git.ignored(root, [path]):
            raise OutsideFolderError(f"{relative} isn't shown.")
    return target


def always_hidden(relative: str) -> bool:
    return any(part in ALWAYS_HIDDEN for part in PurePosixPath(relative).parts)


def sendable(name: str) -> bool:
    """Whether `name` is text the apps can be sent: not a name that isn't UTF-8 (read with surrogates)."""
    try:
        name.encode()
    except UnicodeEncodeError:
        return False
    return True
