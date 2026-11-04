"""The extras' plugins for what the user said they mainly want help with in the About you step
(core/memory/about_you.py): the apps offer each with the usual install, never install one on their own.
Read from the listing kept between downloads, else from the extras themselves; none when neither can be
read, which only leaves the step without suggestions."""

from dataclasses import dataclass

from langgraph.store.base import BaseStore

from lo9i.core.mcp.install import FoundServer
from lo9i.core.memory.about_you import HelpTopic
from lo9i.core.repositories import contents
from lo9i.core.repositories.contents import RepositoryContents
from lo9i.core.repositories.errors import RepositoryError
from lo9i.core.repositories.known import EXTRAS
from lo9i.core.skills.install import FoundSkill

# Email is every mail provider plugin (an `email:` section) instead: the user picks theirs.
_PLUGINS: dict[HelpTopic, tuple[str, ...]] = {
    "calendar": ("calendar",),
    "coding": ("claude-code", "copilot"),
    "expenses": ("expenses",),
    "media": ("watchlist", "youtube"),
    "hosts": ("hosts",),
}


@dataclass(frozen=True)
class Suggested:
    """The plugins for one topic not installed here."""

    topic: HelpTopic
    servers: list[FoundServer]
    skills: list[FoundSkill]


async def suggested(store: BaseStore, topics: list[HelpTopic]) -> list[Suggested]:
    """Each topic with plugins to offer, in the order given."""
    if not topics:
        return []
    try:
        listing = await contents.kept(store, EXTRAS) or await contents.browse(store, EXTRAS)
    except RepositoryError:
        return []
    found = [_for(listing, topic) for topic in dict.fromkeys(topics)]
    return [s for s in found if s.servers or s.skills]


def _for(listing: RepositoryContents, topic: HelpTopic) -> Suggested:
    if topic == "email":
        return Suggested(topic, _mail_providers(listing), [])
    names = _PLUGINS.get(topic, ())
    servers = [s for s in listing.servers if s.name in names and not s.installed]
    return Suggested(topic, servers, [s for s in listing.skills if s.name in names and not s.installed])


def _mail_providers(listing: RepositoryContents) -> list[FoundServer]:
    """None once one is installed: an account needs only its own."""
    providers = [s for s in listing.servers if s.email]
    return [] if any(p.installed for p in providers) else providers
