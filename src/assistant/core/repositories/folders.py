"""Copying a folder out of a repository into the assistant's data: regular, visible files only.
Hidden names (starting with a dot) never come along: `.git` stays out, and the install record
(`source.py`) is written by the assistant."""

import shutil
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from assistant.core.i18n import said
from assistant.core.repositories import source as folder_source
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.source import Source

# What makes a repository folder a skill or an MCP server. A server's folder can also have a
# SKILL.md: that skill is part of the server (core/mcp/install.py).
SKILL_FILE = "SKILL.md"
SERVER_FILE = "server.yaml"
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


def put(source_folder: Path, target: Path, source: Source, only: list[str] | None = None) -> None:
    """Replace `target` with a copy of `source_folder` (or just the files in `only`) and record where
    it came from."""

    def fill(staging: Path) -> None:
        copy_files(source_folder, staging, only)
        folder_source.write(staging, source)

    build(target, fill)


def build(target: Path, fill: Callable[[Path], None]) -> None:
    """Replace `target` with the folder `fill` writes. Built next to the target and swapped in, so a
    failure leaves the old folder as it was."""
    staging = target.with_name(f".{target.name}.installing")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        fill(staging)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(target, ignore_errors=True)
    staging.rename(target)


def copy_files(source: Path, folder: Path, only: list[str] | None = None) -> None:
    """Copy `source`'s regular, visible files (or those in `only`) into `folder`. Raises RepositoryError
    past MAX_FILES or MAX_BYTES."""
    paths = files_in(source)
    paths = [p for p in paths if only is None or p.relative_to(source).as_posix() in only]
    if len(paths) > MAX_FILES or sum(p.stat().st_size for p in paths) > MAX_BYTES:
        raise RepositoryError(
            said(
                "{name} has more than {files} files or {megabytes} MB.",
                name=source.name,
                files=MAX_FILES,
                megabytes=MAX_BYTES // 1000000,
            )
        )
    for path in paths:
        target = folder / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def files_in(source: Path) -> list[Path]:
    """The regular, visible files in a folder and the folders inside it, sorted; links never count."""
    paths = [p for p in sorted(source.rglob("*")) if p.is_file() and not p.is_symlink()]
    return [p for p in paths if valid_path(p.relative_to(source).as_posix())]


def _visible(path: Path) -> bool:
    return not path.is_symlink() and _valid_part(path.name)


def _valid_part(part: str) -> bool:
    return 0 < len(part) <= 100 and not part.startswith(".") and "\\" not in part
