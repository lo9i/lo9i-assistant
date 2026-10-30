"""What a repository offers, skills and MCP servers together, and installing a choice of them from
one download. Everything is checked before anything is written. What it offers is kept and only
downloaded again when the repository has a newer commit (cache.py)."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from langgraph.store.base import BaseStore

from assistant.core.channels import legacy
from assistant.core.i18n import said
from assistant.core.integrations.email import accounts as email_accounts
from assistant.core.mcp import data_key, keys, servers
from assistant.core.mcp import install as server_install
from assistant.core.mcp.install import FoundServer, ServerValues
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.repositories import cache
from assistant.core.repositories import checkout as git
from assistant.core.repositories.cache import Listing
from assistant.core.repositories.errors import RepositoryError
from assistant.core.secret_store import SecretBox
from assistant.core.skills import install as skill_install
from assistant.core.skills.install import FoundSkill
from assistant.core.skills.store import Skill


@dataclass
class RepositoryContents:
    skills: list[FoundSkill]
    servers: list[FoundServer]
    # A plugin that can't be read, one line each (its file and why): only it is left out.
    problems: list[str] = field(default_factory=list)
    # When the repository was last reached (ISO, UTC); "" if not since this was first recorded.
    checked: str = ""


@dataclass
class Installed:
    skills: list[Skill]
    servers: list[McpServer]


def in_language(found: RepositoryContents, language: str) -> RepositoryContents:
    """With its servers' text in `language` where their server.yaml translates it (install.in_language)."""
    return replace(found, servers=[server_install.in_language(s, language) for s in found.servers])


async def browse(store: BaseStore, url: str, token: str = "") -> RepositoryContents:
    """What the repository offers, each saying whether it's installed here from it. `token` reads a
    private repository."""
    return await _with_state(store, url, await _listing(store, url, token))


async def kept(store: BaseStore, url: str) -> RepositoryContents | None:
    """What the repository offered when it was last read, without reaching it; None if never read."""
    listing = await cache.load(store, url)
    return await _with_state(store, url, listing) if listing else None


async def _with_state(store: BaseStore, url: str, listing: Listing) -> RepositoryContents:
    installed = {s.name for s in await servers.load_all(store) if s.source == url}
    found = [await _with_server_state(store, s, s.name in installed) for s in listing.servers]
    skills = [await _with_skill_state(s, url) for s in listing.skills]
    return RepositoryContents(skills, found, listing.problems, listing.checked)


async def _with_server_state(store: BaseStore, server: FoundServer, installed: bool) -> FoundServer:
    version = await asyncio.to_thread(server_install.installed_version, server.name) if installed else ""
    # Fields that may be left empty: a value is saved for them already (kept keys, or old settings).
    saved = await keys.names(store, server.name)
    kept = [f.key for f in server.fields if f.key in saved]
    known = sorted({*await legacy.known_fields(store, server.name), *kept})
    return replace(server, installed=installed, installed_version=version, known_fields=known)


async def _with_skill_state(skill: FoundSkill, url: str) -> FoundSkill:
    version = await asyncio.to_thread(skill_install.installed_version, skill.name, url)
    return replace(skill, installed=version is not None, installed_version=version or "")


async def _listing(store: BaseStore, url: str, token: str) -> Listing:
    """The kept listing while the repository's latest commit is the same, or while it can't be
    reached; a fresh download otherwise. Either way a repository reached is saved as checked now."""
    kept = await cache.load(store, url)
    try:
        commit = await git.latest_commit(url, token)
    except RepositoryError:
        if kept is not None:
            return kept
        raise
    listing = kept if kept is not None and kept.commit == commit else await _download(url, token)
    listing = replace(listing, checked=datetime.now(UTC).isoformat())
    await cache.save(store, url, listing)
    return listing


async def _download(url: str, token: str) -> Listing:
    async with git.checkout(url, token) as (root, commit):
        skills, (found_servers, problems) = await asyncio.to_thread(_find, root, url)
    if not skills and not found_servers and not problems:
        raise RepositoryError(
            said(
                "No skills or MCP servers there: a skill is a folder with a SKILL.md, a server a folder with a "
                "server.yaml."
            )
        )
    return Listing(commit, [c.found() for c in skills.values()], [c.found for c in found_servers.values()], problems)


# Runs a server's check of the values it was given (core/mcp/checks.py); raises McpServerError when they don't work.
Check = Callable[[McpServer], Awaitable[None]]


async def install(
    store: BaseStore,
    box: SecretBox,
    url: str,
    skills: list[str],
    wanted: list[ServerValues],
    token: str = "",
    check: Check | None = None,
) -> Installed:
    """A field left empty takes the key kept from an earlier install. Each server's `check` runs before anything
    is saved; when one fails, the servers this installed are taken out again and nothing is. Raises
    RepositoryError, SkillError or McpServerError, saying what's wrong."""
    if not skills and not wanted:
        raise RepositoryError(said("Pick at least one skill or MCP server to install."))
    wanted = [await legacy.fill(store, w) for w in wanted]
    wanted = [ServerValues(w.name, await keys.given(store, box, w.name, w.values)) for w in wanted]
    before = {s.name for s in await servers.load_all(store)}
    async with git.checkout(url, token) as (root, commit):
        found_skills, (found_servers, _) = await asyncio.to_thread(_find, root, url)
        await asyncio.to_thread(skill_install.check, skills, found_skills, url)
        await server_install.check(store, wanted, found_servers, url)
        new = [await server_install.install(found_servers[w.name], w.values, url, commit) for w in wanted]
        await _checked(store, box, new, check, before)
        installed = [await asyncio.to_thread(skill_install.install, found_skills[n], url, commit) for n in skills]
    for server in new:
        await keys.save(store, box, server)
        await legacy.hand_over(store, server.name)
        if any(p.get("custom") for p in server.email_providers):
            await email_accounts.adopt_hand_entered(store, server.name)
    return Installed(installed, new)


async def _checked(
    store: BaseStore, box: SecretBox, new: list[McpServer], check: Check | None, before: set[str]
) -> None:
    """Raises McpServerError when a server's check says its values don't work, after taking out the code of those
    that weren't installed before. Their data keys are made first, since their checks run with them; like their
    data folders, they stay for installing them again."""
    for server in new:
        await data_key.ensure(store, box, server)
    try:
        for server in new:
            if check is not None:
                await check(server)
    except McpServerError:
        for server in new:
            if server.name not in before:
                await asyncio.to_thread(server_install.uninstall, server.name)
        raise


def _find(
    root: Path, url: str
) -> tuple[dict[str, skill_install.Candidate], tuple[dict[str, server_install.Candidate], list[str]]]:
    return skill_install.find(root, url), server_install.find(root, url)
