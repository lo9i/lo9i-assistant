"""The last listing of a repository's plugins, kept with its commit and when it was last checked, so
the repository is downloaded again only when it has a newer commit, and Plugins shows it at once
while the repository is checked in the background. Whether each plugin is installed isn't kept:
that's local and read fresh every time."""

from dataclasses import asdict, dataclass, field, replace
from typing import Any

from langgraph.store.base import BaseStore

from assistant.core.mcp.install import FoundServer, ServerField
from assistant.core.skills.install import FoundSkill

_NAMESPACE = ("repository_listings",)


@dataclass(frozen=True)
class Listing:
    commit: str
    skills: list[FoundSkill]
    servers: list[FoundServer]
    # A plugin that can't be read, one line each (its file and why); it's left out of the lists.
    problems: list[str] = field(default_factory=list)
    # When the repository was last reached (ISO, UTC), whether or not it had changed; "" if never.
    checked: str = ""


async def load(store: BaseStore, url: str) -> Listing | None:
    item = await store.aget(_NAMESPACE, url)
    if item is None:
        return None
    data = item.value
    skills, servers = [FoundSkill(**s) for s in data["skills"]], [_server(s) for s in data["servers"]]
    return Listing(data["commit"], skills, servers, data.get("problems", []), data.get("checked", ""))


async def save(store: BaseStore, url: str, listing: Listing) -> None:
    skills = [asdict(replace(s, installed=False, installed_version="")) for s in listing.skills]
    servers = [asdict(replace(s, installed=False, installed_version="")) for s in listing.servers]
    value = {"commit": listing.commit, "skills": skills, "servers": servers, "problems": listing.problems}
    await store.aput(_NAMESPACE, url, {**value, "checked": listing.checked})


async def forget(store: BaseStore, url: str) -> None:
    await store.adelete(_NAMESPACE, url)


def _server(data: dict[str, Any]) -> FoundServer:
    return FoundServer(**{**data, "fields": [ServerField(**f) for f in data["fields"]]})
