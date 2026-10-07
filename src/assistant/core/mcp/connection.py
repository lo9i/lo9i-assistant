"""One connection to an MCP server, kept open while the daemon runs and reopened when it drops.

The SDK's client must be opened and closed in the same task, so each connection lives in its own
task (`run`); calls from tools use the open session.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.session import IncomingMessage, MessageHandlerFnT
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.dispatcher import ProgressFnT
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, Implementation, TextContent, Tool, ToolListChangedNotification

from assistant.core.config import settings
from assistant.core.health import HealthLog
from assistant.core.mcp.oauth import McpAuth, SignInNeededError, needs_sign_in
from assistant.core.mcp.servers import McpServer

logger = logging.getLogger(__name__)

_FIRST_RETRY_SECONDS = 30
_MAX_RETRY_SECONDS = 600
_CONNECT_SECONDS = 60
_HTTP_TIMEOUT = httpx2.Timeout(30, read=300)


class NotConnectedError(Exception):
    """The server isn't connected, so nothing was sent."""


class ConnectionLostError(Exception):
    """The server went away during a call; whether the call took effect is unknown."""


@dataclass
class ConnectionState:
    status: str = "connecting"  # connecting, connected, failed, needs_sign_in
    error: str = ""
    tools: list[Tool] = field(default_factory=list)


ClientFactory = Callable[[McpServer, MessageHandlerFnT, httpx2.Auth | None], Client]


def open_client(server: McpServer, on_message: MessageHandlerFnT, auth: httpx2.Auth | None = None) -> Client:
    """A client for the server's transport; `auth` signs a remote server's requests. Stdio servers
    get only a safe baseline of the daemon's environment (the SDK's `get_default_environment`), the
    assistant's time zone, and their own env."""
    target = (
        StdioServerParameters(command=server.command, args=server.args, env={"TZ": settings.timezone, **server.env})
        if server.command
        else _http_transport(server, auth)
    )
    return Client(target, message_handler=on_message, client_info=Implementation(name="lo9i", version="1"))


@asynccontextmanager
async def _http_transport(server: McpServer, auth: httpx2.Auth | None) -> AsyncIterator:
    async with (
        httpx2.AsyncClient(headers=server.headers, timeout=_HTTP_TIMEOUT, auth=auth) as http,
        streamable_http_client(server.url, http_client=http) as streams,
    ):
        yield streams


class McpConnection:
    """Records its failures in `health`: failed connection attempts and failed calls. Only a call
    that works clears them, so a server that connects but breaks on every call still counts as failing.
    A server that asks to sign in isn't failing: it waits for the user, who signs in from the app. One
    whose sign-in stopped working is recorded as signed out, which alerts the user."""

    def __init__(
        self,
        server: McpServer,
        on_change: Callable[[], None],
        health: HealthLog,
        factory: ClientFactory = open_client,
        auth: McpAuth | None = None,
        prepare: Callable[[McpServer], Awaitable[None]] | None = None,
    ) -> None:
        """`prepare` runs before every attempt to connect (core/mcp/environment.py rebuilds a lost environment)."""
        self.server = server
        self._prepare = prepare
        self.state = ConnectionState()
        self._on_change = on_change
        self._health = health
        self._factory = factory
        self._auth = auth
        self._client: Client | None = None
        self._lost = asyncio.Event()
        self._connected = asyncio.Event()
        self._tools_changed = asyncio.Event()

    async def run(self, stop: asyncio.Event) -> None:
        """Stay connected until `stop` is set. A dropped connection is reopened right away; a
        failed attempt is retried after a pause that doubles each time."""
        delay = _FIRST_RETRY_SECONDS
        while not stop.is_set():
            try:
                await self._session(stop)
                delay = _FIRST_RETRY_SECONDS
            except Exception as e:
                if sign_in := needs_sign_in(e):
                    await self._wait_for_sign_in(sign_in, stop)
                    return
                logger.warning("MCP server %s: %s", self.server.name, describe(e))
                self._set(ConnectionState("failed", describe(e)))
                await self._health.failed("mcp", self.server.name, f"Couldn't connect: {describe(e)}")
                await _wait(stop, delay)
                delay = min(delay * 2, _MAX_RETRY_SECONDS)

    async def _wait_for_sign_in(self, error: SignInNeededError, stop: asyncio.Event) -> None:
        """Until stopped: a sign-in restarts the connection (McpHub.restart)."""
        self._set(ConnectionState("needs_sign_in", str(error)))
        if error.lost:
            await self._health.signed_out(self.server.name, str(error))
        await stop.wait()

    async def call(self, tool: str, arguments: dict, progress: ProgressFnT | None = None) -> CallToolResult:
        """Raises MCPError for an error the server reported, NotConnectedError or ConnectionLostError.
        `progress` gets the progress notifications the server sends while the call runs."""
        try:
            result = await self._call(tool, arguments, progress)
        except Exception as e:
            await self._health.failed("mcp", self.server.name, f"{tool}: {describe(e)}")
            raise
        if result.is_error:
            await self._health.failed("mcp", self.server.name, f"{tool}: {_error_text(result)}")
        else:
            await self._health.succeeded("mcp", self.server.name)
        return result

    async def _call(self, tool: str, arguments: dict, progress: ProgressFnT | None) -> CallToolResult:
        client = self._client
        if client is None:
            raise NotConnectedError(self.state.error or self.state.status)
        try:
            return await client.call_tool(tool, arguments, progress_callback=progress)
        except MCPError:
            raise
        except Exception as e:
            self._lost.set()
            raise ConnectionLostError(describe(e)) from e

    async def reconnected(self, timeout: float) -> bool:
        """Wait until the connection is open again."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._connected.wait(), timeout)
        return self._connected.is_set()

    async def _session(self, stop: asyncio.Event) -> None:
        self._set(ConnectionState("connecting"))
        if self._prepare is not None:
            # Outside the connect timeout: rebuilding an environment can take minutes.
            await self._prepare(self.server)
        async with contextlib.AsyncExitStack() as stack:
            async with asyncio.timeout(_CONNECT_SECONDS):
                auth = self._auth.for_connection(self.server) if self._auth else None
                client = await stack.enter_async_context(self._factory(self.server, self._message, auth))
                await self._open(client)
            try:
                await self._serve(client, stop)
            finally:
                self._close()

    async def _open(self, client: Client) -> None:
        tools = await list_tools(client)
        await self._health.signed_in(self.server.name)
        self._client = client
        self._lost.clear()
        self._connected.set()
        self._set(ConnectionState("connected", tools=tools))

    async def _serve(self, client: Client, stop: asyncio.Event) -> None:
        """Until stopped or the connection drops, refresh the tools whenever the server says they changed."""
        while True:
            await _first(stop.wait(), self._lost.wait(), self._tools_changed.wait())
            if stop.is_set() or self._lost.is_set():
                return
            self._tools_changed.clear()
            await self._refresh(client)

    def _close(self) -> None:
        self._client = None
        self._connected.clear()

    async def _message(self, message: IncomingMessage) -> None:
        # Handled in the connection's own task: a request sent from here would wait on the
        # loop that is delivering this message.
        if isinstance(message, ToolListChangedNotification):
            self._tools_changed.set()

    async def _refresh(self, client: Client) -> None:
        try:
            tools = await list_tools(client)
        except Exception as e:
            logger.warning("MCP server %s: couldn't refresh its tools: %s", self.server.name, describe(e))
            return
        self._set(ConnectionState("connected", tools=tools))

    def _set(self, state: ConnectionState) -> None:
        self.state = state
        self._on_change()


async def list_tools(client: Client) -> list[Tool]:
    tools: list[Tool] = []
    cursor: str | None = None
    while True:
        page = await client.list_tools(cursor=cursor, cache_mode="bypass")
        tools += page.tools
        cursor = page.next_cursor
        if not cursor:
            return tools


async def _first(*waits) -> None:
    tasks = [asyncio.ensure_future(w) for w in waits]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), seconds)


def _error_text(result: CallToolResult) -> str:
    text = " ".join(block.text for block in result.content if isinstance(block, TextContent))
    return text or "the tool reported an error"


def describe(error: BaseException) -> str:
    if isinstance(error, BaseExceptionGroup) and error.exceptions:
        return describe(error.exceptions[0])
    return str(error) or type(error).__name__
