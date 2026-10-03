"""Skills in a downloaded repository: finding them, installing them, and updating one later.

A repository can be one skill (SKILL.md at its root) or hold several, one folder each, at its root
or under `skills/`. A folder with a server.yaml is an MCP server, and its SKILL.md is part of it
(core/mcp/install.py), never a skill of its own.

Only the user installs skills, from the app: their scripts run on this computer through bash, so
picking the repository is the user's decision, never the agent's.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from assistant.core.repositories.checkout import checkout, default_name
from assistant.core.repositories.folders import SERVER_FILE, subfolders
from assistant.core.repositories.source import Source
from assistant.core.skills import store
from assistant.core.skills.errors import SkillError


@dataclass(frozen=True)
class FoundSkill:
    """A skill in a repository, before it's installed."""

    name: str
    description: str
    files: list[str]
    # Installed here from the same repository.
    installed: bool = False


@dataclass(frozen=True)
class Candidate:
    skill: store.Skill
    folder: Path
    # Relative to the repository root.
    path: str

    def found(self, url: str) -> FoundSkill:
        return FoundSkill(self.skill.name, self.skill.description, self.skill.files, _installed(self.skill.name, url))


def find(root: Path, url: str) -> dict[str, Candidate]:
    """The repository's skills by name: the root itself, its folders, and the folders in skills/."""
    folders = [root, *subfolders(root), *subfolders(root / "skills")]
    candidates = [_candidate(root, f, default_name(url) if f == root else f.name) for f in folders]
    return {c.skill.name: c for c in candidates if c is not None}


def check(names: list[str], found: dict[str, Candidate], url: str) -> None:
    """Raises SkillError if a name isn't in the repository, or another skill has it. A skill
    installed from the same repository before is replaced."""
    for name in names:
        if name not in found:
            raise SkillError(f"The repository has no skill named {name}.")
        if _taken(name, url):
            raise SkillError(f"You already have a skill named {name}. Delete it first to install this one.")


def install(candidate: Candidate, url: str, commit: str) -> store.Skill:
    return store.put(candidate.skill.name, candidate.folder, Source(url, candidate.path, commit))


async def update(name: str) -> store.Skill:
    """Install the skill again from its repository. Changes made to it here are replaced."""
    source = await asyncio.to_thread(store.installed_from, name)
    if source is None:
        raise SkillError(f"{name} wasn't installed from a repository, so there's nothing to update it from.")
    if source.server:
        raise SkillError(f"{name} comes with the {source.server} MCP server: update the server to update it.")
    async with checkout(source.url) as (root, commit):
        candidate = await asyncio.to_thread(_find_at, root, source.path, name)
        return await asyncio.to_thread(install, candidate, source.url, commit)


def _find_at(root: Path, path: str, name: str) -> Candidate:
    candidate = _candidate(root, root / path, name)
    if candidate is None or candidate.skill.name != name:
        raise SkillError(f"The repository doesn't have {name} at {path} any more.")
    return candidate


def _candidate(root: Path, folder: Path, name: str) -> Candidate | None:
    if folder.is_symlink() or (folder / SERVER_FILE).is_file():
        return None
    skill = store.read(folder, name)
    if skill is None or not store.valid_name(skill.name):
        return None
    return Candidate(skill, folder, folder.relative_to(root).as_posix())


def _installed(name: str, url: str) -> bool:
    try:
        existing = store.load(name)
    except SkillError:
        return False
    return existing.source == url and existing.server is None


def _taken(name: str, url: str) -> bool:
    try:
        existing = store.load(name)
    except SkillError:
        return False
    return existing.builtin or existing.server is not None or existing.source != url
