"""Copying a folder out of a repository into the assistant's data: regular, visible files only.
Hidden names (starting with a dot) never come along: `.git` stays out, and the install record
(`source.py`) is written by the assistant."""

import shutil
from pathlib import Path, PurePosixPath

from assistant.core.repositories import source as folder_source
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.source import Source

MAX_FILES = 100
# All of a folder's files together.
MAX_BYTES = 5_000_000


def valid_path(path: str) -> bool:
    """A relative path inside a folder, with no hidden or odd parts."""
    pure = PurePosixPath(path)
    return bool(pure.parts) and not pure.is_absolute() and all(_valid_part(part) for part in pure.parts)


def subfolders(folder: Path) -> list[Path]:
    """The visible folders in a folder, or none if it doesn't exist."""
    return sorted(p for p in folder.iterdir() if p.is_dir() and _visible(p)) if folder.is_dir() else []


def put(source_folder: Path, target: Path, source: Source) -> None:
    """Replace `target` with a copy of `source_folder` and record where it came from. Built next to
    the target and swapped in, so a failed copy leaves the old folder as it was."""
    staging = target.with_name(f".{target.name}.installing")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        _copy(source_folder, staging)
        folder_source.write(staging, source)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(target, ignore_errors=True)
    staging.rename(target)


def _copy(source: Path, folder: Path) -> None:
    paths = [p for p in sorted(source.rglob("*")) if p.is_file() and not p.is_symlink()]
    paths = [p for p in paths if valid_path(p.relative_to(source).as_posix())]
    if len(paths) > MAX_FILES or sum(p.stat().st_size for p in paths) > MAX_BYTES:
        raise RepositoryError(f"{source.name} has more than {MAX_FILES} files or {MAX_BYTES // 1_000_000} MB.")
    for path in paths:
        target = folder / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _visible(path: Path) -> bool:
    return not path.is_symlink() and _valid_part(path.name)


def _valid_part(part: str) -> bool:
    return 0 < len(part) <= 100 and not part.startswith(".") and "\\" not in part
