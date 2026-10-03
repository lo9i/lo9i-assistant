import builtins
from typing import Any

import httpx

from assistant.client.daemon_client.mcp import status_from_json
from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import (
    FoundServer,
    FoundSkill,
    InstalledFromRepository,
    PluginUpdate,
    RepositoryContents,
    RepositoryError,
    ServerField,
    ServerValues,
    Skill,
)

_ERRORS = {400: RepositoryError}
# Downloading a repository may take up to two minutes (the daemon's limit).
DOWNLOAD_TIMEOUT = httpx.Timeout(150)


class RepositoriesApi:
    """Plugins (MCP servers and skills) from a git repository, the assistant's extras unless one is
    named: look at what it offers, install a choice."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def browse(self, url: str | None = None) -> RepositoryContents:
        """Raises RepositoryError if it can't be read or has nothing to install."""
        data = await self._transport.request(
            "POST", "/repositories/browse", json=_with_url({}, url), errors=_ERRORS, timeout=DOWNLOAD_TIMEOUT
        )
        return RepositoryContents([FoundSkill(**s) for s in data["skills"]], [_server(s) for s in data["servers"]])

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


def _server(data: dict[str, Any]) -> FoundServer:
    return FoundServer(**{**data, "fields": [ServerField(**f) for f in data["fields"]]})


def _with_url(body: dict[str, Any], url: str | None) -> dict[str, Any]:
    """Without a url, the daemon uses the assistant's extras."""
    return {**body, "url": url} if url else body
