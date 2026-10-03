"""MCP servers from any client: adding one after a look at its tools, choosing which tools the agent
gets, trusting it or not, and removing it. Env values and headers never leave the daemon."""

import asyncio
from dataclasses import dataclass, fields, replace

from assistant.core.agent.base import ServiceBase
from assistant.core.mcp import install, servers
from assistant.core.mcp.hub import McpHub, McpToolInfo
from assistant.core.mcp.servers import McpServer, McpServerError

__all__ = [
    "McpMixin",
    "McpServer",
    "McpServerChanges",
    "McpServerError",
    "McpServerStatus",
    "McpToolInfo",
    "mcp_status",
]


@dataclass
class McpServerStatus:
    """What a client shows. Has the names of env values and headers, never the values."""

    name: str
    transport: str
    command: str
    args: list[str]
    url: str
    env_keys: list[str]
    header_keys: list[str]
    enabled: bool
    trusted: bool
    include: list[str]
    exclude: list[str]
    # connecting, connected, failed, off
    status: str
    error: str
    tools: list[McpToolInfo]
    # The repository it was installed from; "" when added by hand.
    source: str = ""


@dataclass
class McpServerChanges:
    """Fields to change; None keeps the current value."""

    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    enabled: bool | None = None
    trusted: bool | None = None
    include: list[str] | None = None
    exclude: list[str] | None = None


class McpMixin(ServiceBase):
    async def mcp_servers(self) -> list[McpServerStatus]:
        return [self._mcp_status(s) for s in await servers.load_all(self._storage.store)]

    async def probe_mcp_server(self, server: McpServer) -> list[McpToolInfo]:
        """The server's tools, to choose from before adding it. Raises McpServerError."""
        return await self.mcp.probe(server)

    async def add_mcp_server(self, server: McpServer) -> McpServerStatus:
        """Raises McpServerError for invalid settings or a name in use."""
        if server.name in {s.name for s in await servers.load_all(self._storage.store)}:
            raise McpServerError(f"There's already an MCP server named {server.name}.")
        return await self._save_mcp_server(server)

    async def update_mcp_server(self, name: str, changes: McpServerChanges) -> McpServerStatus:
        """Raises McpServerError for an unknown server or invalid settings."""
        server = await servers.load(self._storage.store, name)
        values = {f.name: v for f in fields(changes) if (v := getattr(changes, f.name)) is not None}
        return await self._save_mcp_server(replace(server, **values))

    async def remove_mcp_server(self, name: str) -> None:
        """Raises McpServerError for an unknown server."""
        await servers.remove(self._storage.store, name)
        await asyncio.to_thread(install.uninstall, name)
        await self.mcp.reload()

    async def update_mcp_server_from_repository(self, name: str) -> McpServerStatus:
        """Install the server again from its repository, keeping what the user set.
        Raises McpServerError or RepositoryError."""
        server = await install.update(self._storage.store, name)
        await self.mcp.reload()
        return self._mcp_status(server)

    async def _save_mcp_server(self, server: McpServer) -> McpServerStatus:
        await servers.save(self._storage.store, server)
        await self.mcp.reload()
        return self._mcp_status(server)

    def _mcp_status(self, server: McpServer) -> McpServerStatus:
        return mcp_status(self.mcp, server)


def mcp_status(hub: McpHub, server: McpServer) -> McpServerStatus:
    status, error, tools = hub.state(server.name)
    return McpServerStatus(
        name=server.name,
        transport=server.transport,
        command=server.command,
        args=server.args,
        url=server.url,
        env_keys=sorted(server.env),
        header_keys=sorted(server.headers),
        enabled=server.enabled,
        trusted=server.trusted,
        include=server.include,
        exclude=server.exclude,
        status=status,
        error=error,
        tools=tools,
        source=server.source,
    )
