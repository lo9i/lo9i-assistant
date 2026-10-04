"""MCP servers from any client: adding one after a look at its tools, signing in to a remote one,
choosing which tools the agent gets, trusting it or not, and removing it. Env values, headers and
sign-ins never leave the daemon."""

import asyncio
from dataclasses import dataclass, fields, replace

from assistant.core.agent.base import ServiceBase
from assistant.core.integrations.email import accounts as email_accounts
from assistant.core.mcp import install, servers
from assistant.core.mcp.hub import McpHub, McpProbe, McpToolInfo
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.mcp.sign_in import McpSignIn

__all__ = [
    "McpMixin",
    "McpProbe",
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
    # connecting, connected, failed, needs_sign_in (a remote server waiting for the user to sign in), off
    status: str
    error: str
    tools: list[McpToolInfo]
    # The repository it was installed from; "" when added by hand.
    source: str = ""
    # The plugin that added it (core/mcp/install.py); "" when it was added here, by hand.
    plugin: str = ""
    # It comes with a web page, shown in the web app (daemon/pages.py).
    page: bool = False
    # It's a chat channel (core/channels/), set up in its plugin's details in the apps.
    channel: bool = False
    # Failed connection attempts and calls in a row (core/health.py), and the last failure.
    failures: int = 0
    failure: str = ""
    failed_at: str = ""
    # At least FAILING_AFTER in a row: the user was alerted.
    failing: bool = False


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
        return [await self._mcp_status(s) for s in await servers.load_all(self._storage.store)]

    async def probe_mcp_server(self, server: McpServer) -> McpProbe:
        """The server's tools, to choose from before adding it, or that it asks to sign in.
        Raises McpServerError."""
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
        if changes.url is not None and changes.url != server.url:
            # A sign-in belongs to the server at the old URL.
            await self.mcp.sign_out(name)
        return await self._save_mcp_server(replace(server, **values))

    async def start_mcp_sign_in(self, name: str, redirect_uri: str) -> str:
        """The server's sign-in page. The browser comes back to `redirect_uri` (the web app's
        /app/oauth), which calls finish_sign_in. Raises McpServerError."""
        server = await servers.load(self._storage.store, name)
        started = await self.mcp.start_sign_in(server, redirect_uri)
        self._sign_ins.add(started.state, started)
        return started.page

    async def _finish_mcp_sign_in(self, started: McpSignIn, code: str) -> McpServerStatus:
        """Raises SignInError. The server connects again with the new sign-in."""
        await self.mcp.finish_sign_in(started, code)
        return await self._mcp_status(await servers.load(self._storage.store, started.server))

    async def remove_mcp_server(self, name: str, delete_data: bool = False) -> None:
        """Its data stays, for installing it again, unless `delete_data`. Raises McpServerError for
        an unknown server."""
        await servers.remove(self._storage.store, name)
        await asyncio.to_thread(install.uninstall, name)
        await self.mcp.forget(name)
        await self._servers_changed()
        # After the server and its page stopped, so nothing writes there any more. An email
        # plugin's accounts are its data too: without it they're kept, unused, for installing it again.
        if delete_data:
            await asyncio.to_thread(install.delete_data, name)
            await email_accounts.remove_plugin_accounts(self._storage.store, name)

    async def update_mcp_server_from_repository(self, name: str) -> McpServerStatus:
        """Install the server again from its repository, keeping what the user set.
        Raises McpServerError or RepositoryError."""
        server = await install.update(self._storage.store, name)
        # Same command and settings, new code: both run again.
        await self.mcp.restart(name)
        await self.pages.restart(name)
        await self.channel_processes.restart(name)
        await self._servers_changed()
        return await self._mcp_status(server)

    async def _save_mcp_server(self, server: McpServer) -> McpServerStatus:
        await servers.save(self._storage.store, server)
        await self._servers_changed()
        return await self._mcp_status(server)

    async def _mcp_status(self, server: McpServer) -> McpServerStatus:
        return await mcp_status(self.mcp, server)


async def mcp_status(hub: McpHub, server: McpServer) -> McpServerStatus:
    status, error, tools = hub.state(server.name)
    health = await hub.health(server.name)
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
        plugin=server.name if server.source else "",
        page=bool(server.page_command),
        channel=bool(server.channel_command),
        failures=health.failures,
        failure=health.error,
        failed_at=health.at,
        failing=health.failing,
    )
