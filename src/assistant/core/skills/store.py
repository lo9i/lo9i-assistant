import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from assistant.core.config import settings
from assistant.core.repositories import categories, folders, icons, platforms
from assistant.core.repositories import source as skill_source
from assistant.core.skills import files as skill_files
from assistant.core.skills.errors import SkillError as SkillError

# Ships with the app: how to set the assistant up, from each client. Tools point to it when
# something isn't set up.
SETUP = "assistant-setup"

_BUILTIN = Path(__file__).parent / "builtin"
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
# Paths into a skill's folder that its instructions mention, by the usual folder names.
_REFERENCED = re.compile(r"(?<![\w./-])((?:scripts|references|assets)/[\w.-]*\w(?:/[\w.-]*\w)*)")


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
    # The MCP server it comes with, which installs, updates and removes it; None for a skill of its own.
    server: str | None = None
    # What's wrong with it as written (`problems`); empty when nothing is.
    problems: list[str] = field(default_factory=list)
    # `version:` in its SKILL.md; "" when it declares none.
    version: str = ""
    # The plugin that added it: the MCP server it comes with, or itself when it was installed on its
    # own; "" when the user or the assistant wrote it here.
    plugin: str = ""
    # `category:` in its SKILL.md, to group it in the apps (repositories/categories.py).
    category: str = categories.DEFAULT
    # `platforms:` in its SKILL.md, the systems it runs on; empty for all (repositories/platforms.py).
    platforms: list[str] = field(default_factory=list)
    # `icon:` in its SKILL.md (repositories/icons.py); empty when it declares none.
    icon: icons.PluginIcon = field(default_factory=icons.PluginIcon)


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


def check_content(name: str, instructions: str, files: dict[str, str] | None = None) -> None:
    """Raises SkillError if the skill `save` would write has problems: instructions that use a file
    it doesn't have. `files` None means the files it has now."""
    paths = sorted(files) if files is not None else skill_files.listed(_path(name).parent)
    found = problems(instructions, paths)
    if found:
        raise SkillError(" ".join(found))


def problems(instructions: str, files: list[str]) -> list[str]:
    """What would stop a skill from working: instructions that use files it doesn't have."""
    missing = sorted({p for p in _REFERENCED.findall(instructions) if not _has(files, p)})
    return [f"Its instructions use files it doesn't have: {', '.join(missing)}."] if missing else []


def save(name: str, description: str, instructions: str, files: dict[str, str] | None = None) -> Skill:
    """Create or replace a skill. `files` replaces all of its files; None keeps them. Raises
    SkillError for an invalid name or files, or problems in the content."""
    check(name, files)
    check_content(name, instructions, files)
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = yaml.safe_dump({"name": name, "description": description.strip()}, allow_unicode=True).strip()
    path.write_text(f"---\n{header}\n---\n\n{instructions.strip()}\n", encoding="utf-8")
    if files is not None:
        skill_files.replace(path.parent, files)
    return load(name)


def put(name: str, source_folder: Path, source: skill_source.Source, only: list[str] | None = None) -> Skill:
    """Install a skill folder (or the files in `only`) from a repository, replacing a skill of the
    same name."""
    _refuse_builtin(name)
    folders.put(source_folder, _path(name).parent, source, only)
    return load(name)


def installed_from(name: str) -> skill_source.Source | None:
    return None if _is_builtin(name) else skill_source.read(_path(name).parent)


def delete(name: str, server: str = "") -> None:
    """A skill that comes with an MCP server is deleted only by removing that `server`."""
    _refuse_builtin(name)
    target = _path(name).parent
    if not target.exists():
        raise SkillError(f"No skill named {name}.")
    owner = (skill_source.read(target) or skill_source.Source("", "", "")).server
    if owner and owner != server:
        raise SkillError(f"{name} comes with the {owner} MCP server: remove the server to remove it.")
    shutil.rmtree(target)


def skill_in(command: str) -> str | None:
    """The skill whose folder a command uses, by the folder's full path, as `use_skill` gives it."""
    for root in (_root(), _BUILTIN):
        match = re.search(re.escape(str(root)) + r"/([a-z0-9][a-z0-9-]{0,62})/", command)
        if match:
            return match.group(1)
    return None


def valid_name(name: str) -> bool:
    return bool(_NAME.match(name))


def read(skill_folder: Path, default_name: str | None = None) -> Skill | None:
    """The skill in a folder, or None if it has no SKILL.md. Without a name in its SKILL.md, it's
    named `default_name`, or after the folder."""
    path = skill_folder / skill_files.INSTRUCTIONS
    if not path.is_file():
        return None
    meta, body, header_problems = _parse(path.read_text(encoding="utf-8"))
    description = str(meta.get("description") or "")
    files = skill_files.listed(skill_folder)
    source = skill_source.read(skill_folder)
    category, category_problems = _category(meta)
    systems, platform_problems = _platforms(meta)
    icon, icon_problems = _icon(meta, skill_folder)
    return Skill(
        str(meta.get("name") or default_name or skill_folder.name),
        description,
        body.strip(),
        skill_folder.parent == _BUILTIN,
        files,
        source.url if source else None,
        (source.server or None) if source else None,
        [*header_problems, *category_problems, *platform_problems, *icon_problems, *problems(body, files)],
        str(meta.get("version") or ""),
        _plugin(source, str(meta.get("name") or default_name or skill_folder.name)),
        category,
        systems,
        icon,
    )


def _icon(meta: dict, folder: Path) -> tuple[icons.PluginIcon, list[str]]:
    """The icon its SKILL.md declares, or none and the problem with the one it declares."""
    try:
        return icons.parse(meta.get("icon"), folder), []
    except ValueError as e:
        return icons.PluginIcon(), [f"In its SKILL.md, {e}."]


def _platforms(meta: dict) -> tuple[list[str], list[str]]:
    """The platforms its SKILL.md declares, or none and the problem with the ones it declares."""
    try:
        return platforms.parse(meta.get("platforms")), []
    except ValueError as e:
        return [], [f"In its SKILL.md, {e}."]


def _category(meta: dict) -> tuple[str, list[str]]:
    """The category its SKILL.md declares, or the default and the problem with the one it declares."""
    try:
        return categories.parse(meta.get("category"), set()), []
    except ValueError as e:
        return categories.DEFAULT, [f"In its SKILL.md, {e}."]


def _plugin(source: skill_source.Source | None, name: str) -> str:
    if source is None or not source.url:
        return ""
    return source.server or name


def _parse(text: str) -> tuple[dict, str, list[str]]:
    """The SKILL.md header's fields, the instructions, and what's wrong with the header. A broken
    header leaves the skill listed with the problem, instead of breaking every skill list."""
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text, []
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        return {}, match.group(2), [f"The header of its SKILL.md isn't valid YAML: {str(e).splitlines()[0]}."]
    if not isinstance(meta, dict):
        return {}, match.group(2), ["The header of its SKILL.md must be fields like name: and description:."]
    return meta, match.group(2), []


def _has(files: list[str], path: str) -> bool:
    """Whether `path` is one of the files, or a folder holding some."""
    return path in files or any(f.startswith(f"{path}/") for f in files)


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
