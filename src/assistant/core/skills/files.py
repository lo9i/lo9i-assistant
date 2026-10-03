"""The files a skill keeps next to its SKILL.md: scripts, references, templates. Paths are relative
to the skill's folder. Hidden names (starting with a dot) are never skill files: the folder keeps its
install record there (`source.py`), and a repository's `.git` stays out."""

import shutil
from pathlib import Path, PurePosixPath

from assistant.core.skills.errors import SkillError

INSTRUCTIONS = "SKILL.md"
MAX_FILES = 100
# All of a skill's files together.
MAX_BYTES = 5_000_000


def check(files: dict[str, str]) -> None:
    """Raises SkillError for a path outside the folder, a hidden or reserved name, or too much."""
    for path in files:
        if not _valid(PurePosixPath(path)) or path == INSTRUCTIONS:
            raise SkillError(f"{path!r} isn't a valid skill file path. Use a relative path like scripts/report.py.")
    _check_size(len(files), sum(len(content.encode()) for content in files.values()))


def listed(folder: Path) -> list[str]:
    """The skill's files, without SKILL.md."""
    if not folder.is_dir():
        return []
    paths = (p.relative_to(folder) for p in folder.rglob("*") if p.is_file() and not p.is_symlink())
    return sorted(p.as_posix() for p in paths if _valid(PurePosixPath(p.as_posix())) and p.as_posix() != INSTRUCTIONS)


def replace(folder: Path, files: dict[str, str]) -> None:
    """Make `files` the skill's only files. SKILL.md and hidden entries stay."""
    for entry in folder.iterdir():
        if entry.name == INSTRUCTIONS or entry.name.startswith("."):
            continue
        shutil.rmtree(entry) if entry.is_dir() and not entry.is_symlink() else entry.unlink()
    for path, content in files.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def copy(source: Path, folder: Path) -> None:
    """Copy a skill folder from a repository: regular, visible files only, never symlinks."""
    paths = [p for p in sorted(source.rglob("*")) if p.is_file() and not p.is_symlink()]
    paths = [p for p in paths if _valid(PurePosixPath(p.relative_to(source).as_posix()))]
    _check_size(len(paths), sum(p.stat().st_size for p in paths))
    for path in paths:
        target = folder / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _valid(path: PurePosixPath) -> bool:
    parts = path.parts
    return bool(parts) and not path.is_absolute() and all(_valid_part(part) for part in parts)


def _valid_part(part: str) -> bool:
    return 0 < len(part) <= 100 and not part.startswith(".") and "\\" not in part


def _check_size(count: int, size: int) -> None:
    if count > MAX_FILES or size > MAX_BYTES:
        raise SkillError(f"A skill can have at most {MAX_FILES} files and {MAX_BYTES // 1_000_000} MB.")
