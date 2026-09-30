import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from assistant.core.config import settings

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


class SkillError(Exception):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str


def list_skills() -> list[Skill]:
    root = _root()
    files = sorted(root.glob("*/SKILL.md")) if root.exists() else []
    return [skill for skill in map(_read, files) if skill is not None]


def load(name: str) -> Skill:
    skill = _read(_path(name))
    if skill is None:
        raise SkillError(f"No skill named {name}.")
    return skill


def save(name: str, description: str, instructions: str) -> Skill:
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = yaml.safe_dump({"name": name, "description": description.strip()}, allow_unicode=True).strip()
    path.write_text(f"---\n{header}\n---\n\n{instructions.strip()}\n", encoding="utf-8")
    return Skill(name, description.strip(), instructions.strip())


def delete(name: str) -> None:
    folder = _path(name).parent
    if not folder.exists():
        raise SkillError(f"No skill named {name}.")
    shutil.rmtree(folder)


def _root() -> Path:
    return Path(settings.skills_dir).expanduser()


def _path(name: str) -> Path:
    if not _NAME.match(name):
        raise SkillError("Skill names use lowercase letters, digits and hyphens, e.g. news-digest.")
    return _root() / name / "SKILL.md"


def _read(path: Path) -> Skill | None:
    if not path.is_file():
        return None
    match = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
    meta = yaml.safe_load(match.group(1)) if match else {}
    body = match.group(2) if match else path.read_text(encoding="utf-8")
    return Skill(meta.get("name", path.parent.name), meta.get("description", ""), body.strip())
