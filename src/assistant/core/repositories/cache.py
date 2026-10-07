"""The last listing of a repository's plugins, kept with its commit, so the repository is downloaded
again only when it has a newer commit. Whether each plugin is installed isn't kept: that's local and
read fresh every time."""

from dataclasses import asdict, dataclass, replace
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


async def load(store: BaseStore, url: str) -> Listing | None:
    item = await store.aget(_NAMESPACE, url)
    if item is None:
        return None
    data = item.value
    return Listing(data["commit"], [FoundSkill(**s) for s in data["skills"]], [_server(s) for s in data["servers"]])


async def save(store: BaseStore, url: str, listing: Listing) -> None:
    skills = [asdict(replace(s, installed=False, installed_version="")) for s in listing.skills]
    servers = [asdict(replace(s, installed=False, installed_version="")) for s in listing.servers]
    await store.aput(_NAMESPACE, url, {"commit": listing.commit, "skills": skills, "servers": servers})


async def forget(store: BaseStore, url: str) -> None:
    await store.adelete(_NAMESPACE, url)


def _server(data: dict[str, Any]) -> FoundServer:
    return FoundServer(**{**data, "fields": [ServerField(**f) for f in data["fields"]]})
