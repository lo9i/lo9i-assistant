"""The files a skill keeps next to its SKILL.md: scripts, references, templates. Paths are relative
to the skill's folder. Hidden names (starting with a dot) are never skill files: the folder keeps its
install record there (`repositories/source.py`)."""

import shutil
from pathlib import Path

from assistant.core.repositories.folders import MAX_BYTES, MAX_FILES, valid_path
from assistant.core.skills.errors import SkillError

INSTRUCTIONS = "SKILL.md"


def check(files: dict[str, str]) -> None:
    """Raises SkillError for a path outside the folder, a hidden or reserved name, or too much."""
    for path in files:
        if not valid_path(path) or path == INSTRUCTIONS:
            raise SkillError(f"{path!r} isn't a valid skill file path. Use a relative path like scripts/report.py.")
    if len(files) > MAX_FILES or sum(len(content.encode()) for content in files.values()) > MAX_BYTES:
        raise SkillError(f"A skill can have at most {MAX_FILES} files and {MAX_BYTES // 1_000_000} MB.")


def listed(folder: Path) -> list[str]:
    """The skill's files, without SKILL.md."""
    if not folder.is_dir():
        return []
    paths = (p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and not p.is_symlink())
    return sorted(p for p in paths if valid_path(p) and p != INSTRUCTIONS)


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
