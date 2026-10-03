import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from assistant.core.config import settings
from assistant.core.repositories import folders
from assistant.core.repositories import source as skill_source
from assistant.core.skills import files as skill_files
from assistant.core.skills.errors import SkillError as SkillError

# Ships with the app: how to set the assistant up, from each client. Tools point to it when
# something isn't set up.
SETUP = "assistant-setup"

_BUILTIN = Path(__file__).parent / "builtin"
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str
    # Ships with the assistant: it can't be changed or deleted.
    builtin: bool = False
    # Scripts and other files next to SKILL.md, relative to the skill's folder.
    files: list[str] = field(default_factory=list)
    # The git repository it was installed from; None when the assistant or the user wrote it.
    source: str | None = None


def list_skills() -> list[Skill]:
    """Built-in skills first, then the user's."""
    return [*_read_all(_BUILTIN), *[s for s in _read_all(_root()) if not _is_builtin(s.name)]]


def saved_skills() -> list[Skill]:
    """The skills the user or the assistant saved, without the built-in ones. What clients list."""
    return [s for s in _read_all(_root()) if not _is_builtin(s.name)]


def load(name: str) -> Skill:
    skill = read(folder(name))
    if skill is None:
        raise SkillError(f"No skill named {name}.")
    return skill


def folder(name: str) -> Path:
    """The skill's folder, where its SKILL.md and files are."""
    return _BUILTIN / name if _is_builtin(name) else _path(name).parent


def check(name: str, files: dict[str, str] | None = None) -> None:
    """Raises SkillError if `save` would refuse this name or these files."""
    _refuse_builtin(name)
    _path(name)
    if files is not None:
        skill_files.check(files)


def save(name: str, description: str, instructions: str, files: dict[str, str] | None = None) -> Skill:
    """Create or replace a skill. `files` replaces all of its files; None keeps them."""
    check(name, files)
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = yaml.safe_dump({"name": name, "description": description.strip()}, allow_unicode=True).strip()
    path.write_text(f"---\n{header}\n---\n\n{instructions.strip()}\n", encoding="utf-8")
    if files is not None:
        skill_files.replace(path.parent, files)
    return load(name)


def put(name: str, source_folder: Path, source: skill_source.Source) -> Skill:
    """Install a skill folder from a repository, replacing a skill of the same name."""
    _refuse_builtin(name)
    folders.put(source_folder, _path(name).parent, source)
    return load(name)


def installed_from(name: str) -> skill_source.Source | None:
    return None if _is_builtin(name) else skill_source.read(_path(name).parent)


def delete(name: str) -> None:
    _refuse_builtin(name)
    target = _path(name).parent
    if not target.exists():
        raise SkillError(f"No skill named {name}.")
    shutil.rmtree(target)


def valid_name(name: str) -> bool:
    return bool(_NAME.match(name))


def read(skill_folder: Path, default_name: str | None = None) -> Skill | None:
    """The skill in a folder, or None if it has no SKILL.md. Without a name in its SKILL.md, it's
    named `default_name`, or after the folder."""
    path = skill_folder / skill_files.INSTRUCTIONS
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    meta = (yaml.safe_load(match.group(1)) or {}) if match else {}
    body = match.group(2) if match else text
    builtin = skill_folder.parent == _BUILTIN
    source = skill_source.read(skill_folder)
    return Skill(
        meta.get("name", default_name or skill_folder.name),
        meta.get("description", ""),
        body.strip(),
        builtin,
        skill_files.listed(skill_folder),
        source.url if source else None,
    )


def _is_builtin(name: str) -> bool:
    return bool(_NAME.match(name)) and (_BUILTIN / name / skill_files.INSTRUCTIONS).is_file()


def _refuse_builtin(name: str) -> None:
    if _is_builtin(name):
        raise SkillError(f"{name} is built into the assistant and can't be changed or deleted.")


def _read_all(root: Path) -> list[Skill]:
    # Only folders named like a skill: a hidden one is an install in progress.
    folders = sorted(p.parent for p in root.glob("*/SKILL.md") if _NAME.match(p.parent.name)) if root.exists() else []
    return [skill for f in folders if (skill := read(f)) is not None]


def _root() -> Path:
    return Path(settings.skills_dir).expanduser()


def _path(name: str) -> Path:
    if not _NAME.match(name):
        raise SkillError("Skill names use lowercase letters, digits and hyphens, e.g. news-digest.")
    return _root() / name / skill_files.INSTRUCTIONS
