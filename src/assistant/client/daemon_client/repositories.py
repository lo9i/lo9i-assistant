from typing import Any

import httpx

from assistant.client.daemon_client.mcp import status_from_json
from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import (
    FoundServer,
    FoundSkill,
    InstalledFromRepository,
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
    """Skills and MCP servers from a git repository: look at what it offers, install a choice."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def browse(self, url: str) -> RepositoryContents:
        """Raises RepositoryError if it can't be read or has nothing to install."""
        data = await self._transport.request(
            "POST", "/repositories/browse", json={"url": url}, errors=_ERRORS, timeout=DOWNLOAD_TIMEOUT
        )
        return RepositoryContents([FoundSkill(**s) for s in data["skills"]], [_server(s) for s in data["servers"]])

    async def install(self, url: str, skills: list[str], servers: list[ServerValues]) -> InstalledFromRepository:
        """Raises RepositoryError saying what's wrong: a name taken, a field empty, a download failed."""
        body = {"url": url, "skills": skills, "servers": [{"name": s.name, "values": s.values} for s in servers]}
        data = await self._transport.request(
            "POST", "/repositories/install", json=body, errors=_ERRORS, timeout=DOWNLOAD_TIMEOUT
        )
        return InstalledFromRepository(
            [Skill(**s) for s in data["skills"]], [status_from_json(s) for s in data["servers"]]
        )


def _server(data: dict[str, Any]) -> FoundServer:
    return FoundServer(**{**data, "fields": [ServerField(**f) for f in data["fields"]]})
