"""Installing skills from a git repository, and updating them from it later.

A repository can be one skill (SKILL.md at its root) or hold several, one folder each, at its root
or under `skills/`. Only the user installs skills, from the app: their scripts run on this computer
through bash, so picking the repository is the user's decision, never the agent's.
"""

import asyncio
import contextlib
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from assistant.core.skills import store
from assistant.core.skills.errors import SkillError
from assistant.core.skills.source import Source

_TIMEOUT = 120


@dataclass(frozen=True)
class FoundSkill:
    """A skill in a repository, before it's installed."""

    name: str
    description: str
    files: list[str]


@dataclass(frozen=True)
class _Candidate:
    skill: store.Skill
    folder: Path
    # Relative to the repository root.
    path: str


async def browse(url: str) -> list[FoundSkill]:
    """The skills a repository offers."""
    async with _checkout(url) as (root, _):
        found = await asyncio.to_thread(_find, root, url)
    return [FoundSkill(c.skill.name, c.skill.description, c.skill.files) for c in found.values()]


async def install(url: str, names: list[str]) -> list[store.Skill]:
    """Install the named skills from a repository. A skill already installed from it is replaced;
    any other skill with the same name is left alone and the install refused."""
    if not names:
        raise SkillError("Pick at least one skill to install.")
    async with _checkout(url) as (root, commit):
        found = await asyncio.to_thread(_find, root, url)
        await asyncio.to_thread(_check_installable, names, found, url)
        return [await asyncio.to_thread(_put, found[name], url, commit) for name in names]


async def update(name: str) -> store.Skill:
    """Install the skill again from its repository. Changes made to it here are replaced."""
    source = await asyncio.to_thread(store.installed_from, name)
    if source is None:
        raise SkillError(f"{name} wasn't installed from a repository, so there's nothing to update it from.")
    async with _checkout(source.url) as (root, commit):
        candidate = await asyncio.to_thread(_find_at, root, source.path, name)
        return await asyncio.to_thread(_put, candidate, source.url, commit)


@contextlib.asynccontextmanager
async def _checkout(url: str) -> AsyncIterator[tuple[Path, str]]:
    """A fresh copy of the repository's default branch, and its commit."""
    _check_url(url)
    temp = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="lo9i-skills-"))
    try:
        root = temp / "repo"
        commit = await _fetch(url, root)
        yield root, commit
    finally:
        await asyncio.to_thread(shutil.rmtree, temp, True)


def _check_url(url: str) -> None:
    # Only https: other git transports can run local commands or read local files.
    if not url.startswith("https://") or any(c.isspace() for c in url):
        raise SkillError("Give the repository's https:// address, for example https://github.com/user/skills.")


async def _fetch(url: str, root: Path) -> str:
    await _git("clone", "--depth", "1", "--quiet", "--", url, str(root))
    return (await _git("-C", str(root), "rev-parse", "HEAD")).strip()


async def _git(*args: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            # No prompts: a private repository fails instead of waiting for a password nobody types.
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_TERMINAL_PROMPT": "0", "LANG": "C.UTF-8"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise SkillError("Installing skills needs git on the computer running the assistant.") from e
    return await _output(proc)


async def _output(proc: asyncio.subprocess.Process) -> str:
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
    except TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise SkillError(f"The repository didn't download within {_TIMEOUT} seconds.") from e
    if proc.returncode != 0:
        lines = stderr.decode(errors="replace").strip().splitlines()
        raise SkillError(f"Couldn't get the repository: {lines[-1] if lines else 'git failed'}")
    return stdout.decode(errors="replace")


def _find(root: Path, url: str) -> dict[str, _Candidate]:
    """The repository's skills by name: the root itself, its folders, and the folders in skills/."""
    folders = [root, *_subfolders(root), *_subfolders(root / "skills")]
    candidates = [_candidate(root, folder, _default_name(root, folder, url)) for folder in folders]
    found = {c.skill.name: c for c in candidates if c is not None}
    if not found:
        raise SkillError("No skills there: a skill is a folder with a SKILL.md file.")
    return found


def _find_at(root: Path, path: str, name: str) -> _Candidate:
    candidate = _candidate(root, root / path, name)
    if candidate is None or candidate.skill.name != name:
        raise SkillError(f"The repository doesn't have {name} at {path} any more.")
    return candidate


def _subfolders(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")) if folder.is_dir() else []


def _default_name(root: Path, folder: Path, url: str) -> str:
    # A skill without a name in its SKILL.md is named after its folder; the root after the repository.
    return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git").lower() if folder == root else folder.name


def _candidate(root: Path, folder: Path, default_name: str) -> _Candidate | None:
    skill = None if folder.is_symlink() else store.read(folder, default_name)
    if skill is None or not store.valid_name(skill.name):
        return None
    return _Candidate(skill, folder, folder.relative_to(root).as_posix())


def _check_installable(names: list[str], found: dict[str, _Candidate], url: str) -> None:
    for name in names:
        if name not in found:
            raise SkillError(f"The repository has no skill named {name}.")
        if _taken(name, url):
            raise SkillError(f"You already have a skill named {name}. Delete it first to install this one.")


def _taken(name: str, url: str) -> bool:
    try:
        existing = store.load(name)
    except SkillError:
        return False
    return existing.builtin or existing.source != url


def _put(candidate: _Candidate, url: str, commit: str) -> store.Skill:
    return store.put(candidate.skill.name, candidate.folder, Source(url, candidate.path, commit))
