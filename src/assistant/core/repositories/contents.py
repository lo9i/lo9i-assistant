"""What a repository offers, skills and MCP servers together, and installing a choice of them from
one download. Everything is checked before anything is written. What it offers is kept and only
downloaded again when the repository has a newer commit (cache.py)."""

import asyncio
from dataclasses import dataclass, replace
from pathlib import Path

from langgraph.store.base import BaseStore

from assistant.core.mcp import install as server_install
from assistant.core.mcp import servers
from assistant.core.mcp.install import FoundServer, ServerValues
from assistant.core.mcp.servers import McpServer
from assistant.core.repositories import cache
from assistant.core.repositories import checkout as git
from assistant.core.repositories.cache import Listing
from assistant.core.repositories.errors import RepositoryError
from assistant.core.skills import install as skill_install
from assistant.core.skills.install import FoundSkill
from assistant.core.skills.store import Skill


@dataclass
class RepositoryContents:
    skills: list[FoundSkill]
    servers: list[FoundServer]


@dataclass
class Installed:
    skills: list[Skill]
    servers: list[McpServer]


async def browse(store: BaseStore, url: str) -> RepositoryContents:
    """What the repository offers, each saying whether it's installed here from it."""
    return await _with_state(store, url, await _listing(store, url))


async def kept(store: BaseStore, url: str) -> RepositoryContents | None:
    """What the repository offered when it was last read, without reaching it; None if never read."""
    listing = await cache.load(store, url)
    return await _with_state(store, url, listing) if listing else None


async def _with_state(store: BaseStore, url: str, listing: Listing) -> RepositoryContents:
    installed = {s.name for s in await servers.load_all(store) if s.source == url}
    found = [await _with_server_state(s, s.name in installed) for s in listing.servers]
    skills = [await _with_skill_state(s, url) for s in listing.skills]
    return RepositoryContents(skills, found)


async def _with_server_state(server: FoundServer, installed: bool) -> FoundServer:
    version = await asyncio.to_thread(server_install.installed_version, server.name) if installed else ""
    return replace(server, installed=installed, installed_version=version)


async def _with_skill_state(skill: FoundSkill, url: str) -> FoundSkill:
    version = await asyncio.to_thread(skill_install.installed_version, skill.name, url)
    return replace(skill, installed=version is not None, installed_version=version or "")


async def _listing(store: BaseStore, url: str) -> Listing:
    """The kept listing while the repository's latest commit is the same, or while it can't be
    reached; a fresh download otherwise."""
    kept = await cache.load(store, url)
    try:
        commit = await git.latest_commit(url)
    except RepositoryError:
        if kept is not None:
            return kept
        raise
    if kept is not None and kept.commit == commit:
        return kept
    listing = await _download(url)
    await cache.save(store, url, listing)
    return listing


async def _download(url: str) -> Listing:
    async with git.checkout(url) as (root, commit):
        skills, found_servers = await asyncio.to_thread(_find, root, url)
    if not skills and not found_servers:
        raise RepositoryError(
            "No skills or MCP servers there: a skill is a folder with a SKILL.md, a server a folder with a server.yaml."
        )
    return Listing(commit, [c.found() for c in skills.values()], [c.found for c in found_servers.values()])


async def install(store: BaseStore, url: str, skills: list[str], wanted: list[ServerValues]) -> Installed:
    """Raises RepositoryError, SkillError or McpServerError, saying what's wrong."""
    if not skills and not wanted:
        raise RepositoryError("Pick at least one skill or MCP server to install.")
    async with git.checkout(url) as (root, commit):
        found_skills, found_servers = await asyncio.to_thread(_find, root, url)
        await asyncio.to_thread(skill_install.check, skills, found_skills, url)
        await server_install.check(store, wanted, found_servers, url)
        installed = [await asyncio.to_thread(skill_install.install, found_skills[n], url, commit) for n in skills]
        new = [await server_install.install(found_servers[w.name], w.values, url, commit) for w in wanted]
    for server in new:
        await servers.save(store, server)
    return Installed(installed, new)


def _find(root: Path, url: str) -> tuple[dict[str, skill_install.Candidate], dict[str, server_install.Candidate]]:
    return skill_install.find(root, url), server_install.find(root, url)
