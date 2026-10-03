from dataclasses import asdict
from typing import Any

import httpx

from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import McpServer, McpServerChanges, McpServerError, McpServerStatus, McpToolInfo

_ERRORS = {400: McpServerError, 404: McpServerError}
# Connecting to a server may take up to a minute (the daemon's limit).
_CONNECT_TIMEOUT = httpx.Timeout(90)


class McpApi:
    """MCP servers: look at a server's tools, add it, choose its tools, trust it, remove it."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def servers(self) -> list[McpServerStatus]:
        return [_status(s) for s in await self._transport.request("GET", "/mcp/servers")]

    async def probe(self, server: McpServer) -> list[McpToolInfo]:
        data = await self._transport.request(
            "POST", "/mcp/probe", json=_settings(server), errors=_ERRORS, timeout=_CONNECT_TIMEOUT
        )
        return [McpToolInfo(**t) for t in data]

    async def add(self, server: McpServer) -> McpServerStatus:
        data = await self._transport.request("POST", "/mcp/servers", json=_settings(server), errors=_ERRORS)
        return _status(data)

    async def change(self, name: str, changes: McpServerChanges) -> McpServerStatus:
        body = {k: v for k, v in asdict(changes).items() if v is not None}
        return _status(await self._transport.request("PATCH", f"/mcp/servers/{name}", json=body, errors=_ERRORS))

    async def remove(self, name: str) -> None:
        await self._transport.request("DELETE", f"/mcp/servers/{name}", errors=_ERRORS)


def _settings(server: McpServer) -> dict[str, Any]:
    settings = asdict(server)
    settings.pop("enabled")
    return settings


def _status(data: dict[str, Any]) -> McpServerStatus:
    return McpServerStatus(**{**data, "tools": [McpToolInfo(**t) for t in data["tools"]]})
