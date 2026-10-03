from dataclasses import asdict
from typing import Any

import httpx

from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import (
    McpProbe,
    McpServer,
    McpServerChanges,
    McpServerError,
    McpServerStatus,
    McpToolInfo,
)

_ERRORS = {400: McpServerError, 404: McpServerError}
# Connecting to a server may take up to a minute (the daemon's limit).
_CONNECT_TIMEOUT = httpx.Timeout(90)
# Downloading a repository may take up to two minutes.
_DOWNLOAD = httpx.Timeout(150)


class McpApi:
    """MCP servers: look at a server's tools, add it, sign in to it, choose its tools, trust it, remove it."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def servers(self) -> list[McpServerStatus]:
        return [status_from_json(s) for s in await self._transport.request("GET", "/mcp/servers")]

    async def probe(self, server: McpServer) -> McpProbe:
        """Its tools, or that it asks to sign in. Raises McpServerError."""
        data = await self._transport.request(
            "POST", "/mcp/probe", json=_settings(server), errors=_ERRORS, timeout=_CONNECT_TIMEOUT
        )
        return McpProbe([McpToolInfo(**t) for t in data["tools"]], data["sign_in"])

    async def start_sign_in(self, name: str, redirect_uri: str) -> str:
        """The remote server's sign-in page. The browser comes back to `redirect_uri`, the web app's
        /app/oauth, which finishes it (`client.oauth`). Raises McpServerError."""
        body = {"redirect_uri": redirect_uri}
        data = await self._transport.request(
            "POST", f"/mcp/servers/{name}/sign-in", json=body, errors=_ERRORS, timeout=_CONNECT_TIMEOUT
        )
        return data["url"]

    async def add(self, server: McpServer) -> McpServerStatus:
        data = await self._transport.request("POST", "/mcp/servers", json=_settings(server), errors=_ERRORS)
        return status_from_json(data)

    async def change(self, name: str, changes: McpServerChanges) -> McpServerStatus:
        body = {k: v for k, v in asdict(changes).items() if v is not None}
        return status_from_json(
            await self._transport.request("PATCH", f"/mcp/servers/{name}", json=body, errors=_ERRORS)
        )

    async def update_from_repository(self, name: str) -> McpServerStatus:
        """Install the server again from its repository. Raises McpServerError."""
        data = await self._transport.request("POST", f"/mcp/servers/{name}/update", errors=_ERRORS, timeout=_DOWNLOAD)
        return status_from_json(data)

    async def remove(self, name: str, delete_data: bool = False) -> None:
        """Its data stays, for installing it again, unless `delete_data`."""
        params = {"delete_data": "true"} if delete_data else {}
        await self._transport.request("DELETE", f"/mcp/servers/{name}", errors=_ERRORS, params=params)


def _settings(server: McpServer) -> dict[str, Any]:
    settings = asdict(server)
    settings.pop("enabled")
    settings.pop("source")
    return settings


def status_from_json(data: dict[str, Any]) -> McpServerStatus:
    return McpServerStatus(**{**data, "tools": [McpToolInfo(**t) for t in data["tools"]]})
