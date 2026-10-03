import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from assistant.core.config import settings

# Ships with the app: how to set the assistant up, from each client. Tools point to it when
# something isn't set up.
SETUP = "assistant-setup"

_BUILTIN = Path(__file__).parent / "builtin"
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


class SkillError(Exception):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str
    # Ships with the assistant: it can't be changed or deleted.
    builtin: bool = False


def list_skills() -> list[Skill]:
    """Built-in skills first, then the user's."""
    return [*_read_all(_BUILTIN), *[s for s in _read_all(_root()) if not _is_builtin(s.name)]]


def saved_skills() -> list[Skill]:
    """The skills the user or the assistant saved, without the built-in ones. What clients list."""
    return [s for s in _read_all(_root()) if not _is_builtin(s.name)]


def load(name: str) -> Skill:
    builtin = _is_builtin(name)
    skill = _read(_BUILTIN / name / "SKILL.md", builtin) if builtin else _read(_path(name))
    if skill is None:
        raise SkillError(f"No skill named {name}.")
    return skill


def save(name: str, description: str, instructions: str) -> Skill:
    _refuse_builtin(name)
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = yaml.safe_dump({"name": name, "description": description.strip()}, allow_unicode=True).strip()
    path.write_text(f"---\n{header}\n---\n\n{instructions.strip()}\n", encoding="utf-8")
    return Skill(name, description.strip(), instructions.strip())


def delete(name: str) -> None:
    _refuse_builtin(name)
    folder = _path(name).parent
    if not folder.exists():
        raise SkillError(f"No skill named {name}.")
    shutil.rmtree(folder)


def _is_builtin(name: str) -> bool:
    return bool(_NAME.match(name)) and (_BUILTIN / name / "SKILL.md").is_file()


def _refuse_builtin(name: str) -> None:
    if _is_builtin(name):
        raise SkillError(f"{name} is built into the assistant and can't be changed or deleted.")


def _read_all(root: Path) -> list[Skill]:
    files = sorted(root.glob("*/SKILL.md")) if root.exists() else []
    return [skill for path in files if (skill := _read(path, root == _BUILTIN)) is not None]


def _root() -> Path:
    return Path(settings.skills_dir).expanduser()


def _path(name: str) -> Path:
    if not _NAME.match(name):
        raise SkillError("Skill names use lowercase letters, digits and hyphens, e.g. news-digest.")
    return _root() / name / "SKILL.md"


def _read(path: Path, builtin: bool = False) -> Skill | None:
    if not path.is_file():
        return None
    match = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
    meta = yaml.safe_load(match.group(1)) if match else {}
    body = match.group(2) if match else path.read_text(encoding="utf-8")
    return Skill(meta.get("name", path.parent.name), meta.get("description", ""), body.strip(), builtin)
