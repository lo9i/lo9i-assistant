import builtins
from dataclasses import asdict
from typing import Any

import httpx

from assistant.client.daemon_client.mcp import status_from_json
from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import (
    FoundServer,
    FoundSkill,
    InstalledFromRepository,
    KeptKeys,
    PluginUpdate,
    Repository,
    RepositoryContents,
    RepositoryError,
    RepositoryPlugins,
    ServerField,
    ServerValues,
    Skill,
)

_ERRORS = {400: RepositoryError}
# Downloading a repository may take up to two minutes (the daemon's limit).
DOWNLOAD_TIMEOUT = httpx.Timeout(150)


class RepositoriesApi:
    """Plugins (MCP servers and skills) from a git repository, the assistant's extras unless one is
    named: look at what it offers, install a choice. And the repositories plugins are listed from: the
    official extras and the ones the user adds."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def forget_keys(self, kept: KeptKeys) -> None:
        """Delete what a removed plugin left kept."""
        await self._transport.request("POST", "/plugins/keys/forget", json=asdict(kept))

    async def list(self) -> builtins.list[Repository]:
        return [Repository(**r) for r in await self._transport.request("GET", "/repositories")]

    async def add(self, url: str, token: str = "") -> Repository:
        """`token` reads a private repository. Raises RepositoryError when it's listed already, can't be
        read, or offers no plugins."""
        body = {"url": url, "token": token} if token else {"url": url}
        data = await self._transport.request(
            "POST", "/repositories", json=body, errors=_ERRORS, timeout=DOWNLOAD_TIMEOUT
        )
        return Repository(**data)

    async def remove(self, url: str) -> None:
        """Its installed plugins stay. Raises RepositoryError for the extras or one not listed."""
        await self._transport.request("POST", "/repositories/remove", json={"url": url}, errors=_ERRORS)

    async def plugins(self, cached: bool = False) -> builtins.list[RepositoryPlugins]:
        """What every listed repository offers; one that can't be read has an error instead.
        `cached`: as each one offered it when last read, reaching only those never read."""
        params = {"cached": "true"} if cached else None
        data = await self._transport.request("GET", "/repositories/plugins", params=params, timeout=DOWNLOAD_TIMEOUT)
        return [
            RepositoryPlugins(
                Repository(**r["repository"]), _contents(r["contents"]) if r["contents"] else None, r["error"]
            )
            for r in data
        ]

    async def browse(self, url: str | None = None) -> RepositoryContents:
        """Raises RepositoryError if it can't be read or has nothing to install."""
        data = await self._transport.request(
            "POST", "/repositories/browse", json=_with_url({}, url), errors=_ERRORS, timeout=DOWNLOAD_TIMEOUT
        )
        return _contents(data)

    async def install(
        self, skills: builtins.list[str], servers: builtins.list[ServerValues], url: str | None = None
    ) -> InstalledFromRepository:
        """Raises RepositoryError saying what's wrong: a name taken, a field empty, a download failed."""
        body = _with_url({"skills": skills, "servers": [{"name": s.name, "values": s.values} for s in servers]}, url)
        data = await self._transport.request(
            "POST", "/repositories/install", json=body, errors=_ERRORS, timeout=DOWNLOAD_TIMEOUT
        )
        return InstalledFromRepository(
            [Skill(**s) for s in data["skills"]], [status_from_json(s) for s in data["servers"]]
        )

    async def updates(self) -> builtins.list[PluginUpdate]:
        """Installed plugins the extras have a newer version of, as of the daemon's last check."""
        return [PluginUpdate(**u) for u in await self._transport.request("GET", "/repositories/updates")]

    async def update_checks(self) -> bool:
        """Whether the daemon checks the extras for plugin updates in the background."""
        return (await self._transport.request("GET", "/settings/plugin-updates"))["enabled"]

    async def set_update_checks(self, enabled: bool) -> bool:
        data = await self._transport.request("PUT", "/settings/plugin-updates", json={"enabled": enabled})
        return data["enabled"]


def _contents(data: dict[str, Any]) -> RepositoryContents:
    skills, servers = [FoundSkill(**s) for s in data["skills"]], [_server(s) for s in data["servers"]]
    return RepositoryContents(skills, servers, data["problems"], data["checked"])


def _server(data: dict[str, Any]) -> FoundServer:
    return FoundServer(**{**data, "fields": [ServerField(**f) for f in data["fields"]]})


def offered_plugin(request: dict[str, Any]) -> FoundServer | FoundSkill:
    """The plugin in a request the agent paused for (core/events.py::PLUGIN_OFFER)."""
    return _server(request["server"]) if "server" in request else FoundSkill(**request["skill"])


def _with_url(body: dict[str, Any], url: str | None) -> dict[str, Any]:
    """Without a url, the daemon uses the assistant's extras."""
    return {**body, "url": url} if url else body
