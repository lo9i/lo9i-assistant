"""Plugins the agent can offer the user (core/tools/plugins.py): what the assistant's extras have that
isn't installed here. Read from the listing kept between downloads (core/repositories/cache.py), which
the update checker refreshes daily, so building the system prompt never reaches the network."""

from dataclasses import dataclass

from langgraph.store.base import BaseStore

from assistant.core.mcp.install import FoundServer
from assistant.core.repositories import contents
from assistant.core.repositories.contents import RepositoryContents
from assistant.core.repositories.errors import RepositoryError
from assistant.core.repositories.known import EXTRAS
from assistant.core.skills.install import FoundSkill


@dataclass(frozen=True)
class Offer:
    name: str
    description: str


async def offerable(store: BaseStore) -> list[Offer]:
    """The extras' plugins not installed here, as last read; none if they were never read."""
    kept = await contents.kept(store, EXTRAS)
    return [Offer(p.name, p.description) for p in _plugins(kept) if not p.installed] if kept else []


async def find(store: BaseStore, name: str) -> FoundServer | FoundSkill | None:
    """The plugin named `name`, from the kept listing or, when that doesn't have it, the extras
    themselves. Raises RepositoryError when they can't be read."""
    kept = await contents.kept(store, EXTRAS)
    found = _named(kept, name) if kept else None
    return found or _named(await contents.browse(store, EXTRAS), name)


async def names(store: BaseStore) -> list[str]:
    """Every plugin the extras have, as last read; empty when they can't be read either."""
    try:
        listing = await contents.kept(store, EXTRAS) or await contents.browse(store, EXTRAS)
    except RepositoryError:
        return []
    return sorted(p.name for p in _plugins(listing))


async def email_providers(store: BaseStore) -> list[FoundServer]:
    """The extras' mail provider plugins, installed or not. Raises RepositoryError when they can't be read."""
    listing = await contents.kept(store, EXTRAS) or await contents.browse(store, EXTRAS)
    return [s for s in listing.servers if s.email]


def _plugins(listing: RepositoryContents) -> list[FoundServer | FoundSkill]:
    return [*listing.servers, *listing.skills]


def _named(listing: RepositoryContents, name: str) -> FoundServer | FoundSkill | None:
    return next((p for p in _plugins(listing) if p.name == name), None)
