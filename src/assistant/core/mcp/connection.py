"""One connection to an MCP server, kept open while the daemon runs and reopened when it drops.

The SDK's client must be opened and closed in the same task, so each connection lives in its own
task (`run`); calls from tools use the open session.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.session import IncomingMessage, MessageHandlerFnT
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, Implementation, Tool, ToolListChangedNotification

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
    status: str = "connecting"  # connecting, connected, failed
    error: str = ""
    tools: list[Tool] = field(default_factory=list)


ClientFactory = Callable[[McpServer, MessageHandlerFnT], Client]


def open_client(server: McpServer, on_message: MessageHandlerFnT) -> Client:
    """A client for the server's transport. Stdio servers get only a safe baseline of the
    daemon's environment plus their own env (the SDK's `get_default_environment`)."""
    target = (
        StdioServerParameters(command=server.command, args=server.args, env=server.env or None)
        if server.command
        else _http_transport(server)
    )
    return Client(target, message_handler=on_message, client_info=Implementation(name="lo9i", version="1"))


@asynccontextmanager
async def _http_transport(server: McpServer) -> AsyncIterator:
    async with (
        httpx2.AsyncClient(headers=server.headers, timeout=_HTTP_TIMEOUT) as http,
        streamable_http_client(server.url, http_client=http) as streams,
    ):
        yield streams


class McpConnection:
    def __init__(self, server: McpServer, on_change: Callable[[], None], factory: ClientFactory = open_client) -> None:
        self.server = server
        self.state = ConnectionState()
        self._on_change = on_change
        self._factory = factory
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
                logger.warning("MCP server %s: %s", self.server.name, describe(e))
                self._set(ConnectionState("failed", describe(e)))
                await _wait(stop, delay)
                delay = min(delay * 2, _MAX_RETRY_SECONDS)

    async def call(self, tool: str, arguments: dict) -> CallToolResult:
        """Raises MCPError for an error the server reported, NotConnectedError or ConnectionLostError."""
        client = self._client
        if client is None:
            raise NotConnectedError(self.state.error or self.state.status)
        try:
            return await client.call_tool(tool, arguments)
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
        async with contextlib.AsyncExitStack() as stack:
            async with asyncio.timeout(_CONNECT_SECONDS):
                client = await stack.enter_async_context(self._factory(self.server, self._message))
                await self._open(client)
            try:
                await self._serve(client, stop)
            finally:
                self._close()

    async def _open(self, client: Client) -> None:
        tools = await list_tools(client)
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


def describe(error: BaseException) -> str:
    if isinstance(error, BaseExceptionGroup) and error.exceptions:
        return describe(error.exceptions[0])
    return str(error) or type(error).__name__
