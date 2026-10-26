"""The connected MCP servers and the tools they give the agent.

The daemon runs the hub as a supervised task. The graph reads three things from it: the list of servers
and their tools' names, which the system prompt shows; the definitions of the tools a conversation loaded,
which its epoch keeps in state so the tool list changes only when it loads more; and the tool to run for a
call, looked up live so a tool turned off stops working at once.
Local servers run on demand (core/mcp/on_demand.py); remote ones stay connected.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import Collection
from dataclasses import dataclass
from functools import partial
from typing import Any

from langgraph.store.base import BaseStore
from mcp.client.session import IncomingMessage
from mcp.shared.dispatcher import ProgressFnT
from mcp.types import CallToolResult, Tool

from assistant.core.background import BackgroundEnds
from assistant.core.bus import EventBus
from assistant.core.context import McpStarts
from assistant.core.health import Health, HealthLog
from assistant.core.hidden_text import strip_hidden
from assistant.core.mcp import background, data_key, keys, logins, servers, sign_in, ssh_agent, tool_cache
from assistant.core.mcp.background import WorkFinished
from assistant.core.mcp.connection import (
    ClientFactory,
    McpConnection,
    NotConnectedError,
    describe,
    list_tools,
    open_client,
)
from assistant.core.mcp.environment import Environments
from assistant.core.mcp.logins import SharedLogins
from assistant.core.mcp.media import ToolMedia
from assistant.core.mcp.oauth import McpAuth, needs_sign_in
from assistant.core.mcp.on_demand import OnDemand
from assistant.core.mcp.sanitize import MAX_TOOL_NAME, tool_name
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.mcp.sign_in import McpSignIn
from assistant.core.mcp.tools import McpTool
from assistant.core.secret_store import SecretBox

logger = logging.getLogger(__name__)

_PROBE_SECONDS = 60
# Changing these needs a new connection; the others (tool selection, trust) apply at once.
_CONNECTION_FIELDS = ("command", "args", "env", "url", "headers")


@dataclass
class McpToolInfo:
    name: str
    description: str
    read_only: bool
    selected: bool


@dataclass
class McpProbe:
    tools: list[McpToolInfo]
    # The server asks to sign in: it can be added, and its tools show up once the user signs in.
    sign_in: bool = False


@dataclass
class _Running:
    connection: McpConnection
    stop: asyncio.Event
    task: asyncio.Task


class McpHub(McpStarts):
    name = "mcp"

    def __init__(
        self,
        store: BaseStore,
        bus: EventBus,
        health: HealthLog,
        media: ToolMedia,
        auth: McpAuth,
        secrets: SecretBox,
        factory: ClientFactory | None = None,
        shared: SharedLogins | None = None,
        environments: Environments | None = None,
        background: BackgroundEnds | None = None,
    ) -> None:
        """`shared` gives the logins servers can use instead of their own (core/mcp/logins.py);
        `environments` rebuilds a server's lost environment before it starts. `secrets` reads the
        servers' keys (keys.py) to connect them. `background` tells the servers' background work that
        finished to the conversation that started it."""
        self._environments = environments
        self._background = background
        self._store = store
        self._secrets = secrets
        self._shared = shared or dict
        self._bus = bus
        self._factory = factory or open_client
        self._health = health
        self._media = media
        self._auth = auth
        self._running: dict[str, _Running] = {}
        # The sign-in in progress per server; starting another drops it.
        self._signing_in: dict[str, McpSignIn] = {}
        self._tools: dict[str, McpTool] = {}
        self._active = False

    async def run(self, stop: asyncio.Event) -> None:
        """Connect the enabled servers and keep them connected until `stop` is set."""
        self._active = True
        try:
            await self.reload()
            await stop.wait()
        finally:
            self._active = False
            await self._stop_all()

    async def reload(self) -> None:
        """Bring the connections in line with the saved servers. Called after every change."""
        if not self._active:
            return
        enabled = [s for s in await servers.load_all(self._store) if s.enabled and s.is_mcp]
        saved = [
            await data_key.with_key(self._store, self._secrets, s)
            for s in await keys.fill_all(self._store, self._secrets, enabled)
        ]
        wanted = {s.name: ssh_agent.with_agent(logins.with_login(s, self._shared())) for s in saved}
        for name in [n for n in self._running if n not in wanted]:
            await self._stop(name)
        for server in wanted.values():
            await self._apply(server)
        self._changed()

    async def restart(self, name: str) -> None:
        """Connect to the server again even if its settings didn't change: its code did (an update), so its
        tools are learned again."""
        await tool_cache.forget(self._store, name)
        if self._active and name in self._running:
            await self._stop(name)
        await self.reload()

    def definitions(self, servers: Collection[str]) -> list[dict[str, Any]]:
        """The definitions of these servers' tools for the model, in a stable order. A conversation loads a
        server's tools when it needs them (core/plugin_loading.py)."""
        return [_definition(tool) for _, tool in sorted(self._tools.items()) if tool.connection.server.name in servers]

    def catalog(self) -> dict[str, list[str]]:
        """Each server with tools, and their names without the server's prefix, for the list a conversation
        loads them from."""
        catalog: dict[str, list[str]] = {}
        for name, tool in sorted(self._tools.items()):
            server = tool.connection.server.name
            catalog.setdefault(server, []).append(name.removeprefix(tool_name(server, "")))
        return catalog

    def server_of(self, name: str) -> str | None:
        """The server whose tool the model sees under `name`."""
        tool = self._tools.get(name)
        return tool.connection.server.name if tool else None

    def read_only_definitions(self) -> list[dict[str, Any]]:
        """Definitions of the tools that say they only read, for subagents and Home's sections."""
        return [_definition(tool) for _, tool in sorted(self._tools.items()) if tool.read_only]

    def tool(self, name: str) -> McpTool | None:
        return self._tools.get(name)

    async def call(
        self, server: str, tool: str, arguments: dict[str, Any], progress: ProgressFnT | None = None
    ) -> CallToolResult:
        """Calls a server's tool directly, not through the model: no approval and no selection apply,
        as for a conversation the user handed to the server's agent (core/conversation/handoffs.py).
        Raises NotConnectedError when the server isn't connected, and what McpConnection.call raises."""
        running = self._running.get(server)
        if running is None:
            raise NotConnectedError(f"{server} isn't running. Turn it on in Plugins.")
        return await running.connection.call(tool, arguments, progress)

    def unavailable(self, name: str) -> str:
        """Why a tool this epoch offers can't run now, for the model."""
        for running in self._running.values():
            connection = running.connection
            if not name.startswith(tool_name(connection.server.name, "")):
                continue
            if connection.state.tools:
                return f"{name} was turned off, or {connection.server.name} no longer has it."
            state = connection.state
            reason = f"{state.status}: {state.error}" if state.error else state.status
            return f"{connection.server.name} isn't connected ({reason}). Its tools can't run now."
        return f"{name} isn't available: its MCP server was removed or turned off."

    def state(self, name: str) -> tuple[str, str, list[McpToolInfo]]:
        """A server's status (connecting, connected, failed, needs_sign_in, idle, off), error and tools."""
        running = self._running.get(name)
        if running is None:
            return "off", "", []
        connection = running.connection
        tools = [_info(connection.server, tool) for tool in connection.state.tools]
        return connection.state.status, connection.state.error, tools

    async def started(self, name: str, timeout: float) -> str:
        """A server just installed or turned on: its first start can be slow (an environment to build) and
        can time out once before a retry connects. One on demand that already stopped again is idle."""
        running = self._running.get(name)
        if running is not None and running.connection.state.status in ("connecting", "failed"):
            await running.connection.reconnected(timeout)
        return self.state(name)[0]

    async def health(self, name: str) -> Health:
        return await self._health.get("mcp", name)

    async def forget(self, name: str) -> None:
        """Drop the failures and the sign-in of a removed server, so one added later under its name
        starts clean."""
        await self._health.forget("mcp", name)
        await tool_cache.forget(self._store, name)
        await self.sign_out(name)

    async def sign_out(self, name: str) -> None:
        await self._auth.forget(name)

    async def probe(self, server: McpServer) -> McpProbe:
        """Connect once to list a server's tools, before it's saved. Raises McpServerError."""
        servers.validate(server)
        try:
            async with (
                asyncio.timeout(_PROBE_SECONDS),
                self._factory(server, _ignore, self._auth.for_connection(server), ()) as client,
            ):
                tools = await list_tools(client)
        except Exception as e:
            if needs_sign_in(e):
                return McpProbe([], sign_in=True)
            reason = f"no answer within {_PROBE_SECONDS}s" if isinstance(e, TimeoutError) else describe(e)
            raise McpServerError(f"Couldn't connect to {server.name}: {reason}") from e
        return McpProbe([_info(server, tool) for tool in tools])

    async def start_sign_in(self, server: McpServer, redirect_uri: str) -> McpSignIn:
        """Raises McpServerError for a local server, one that can't be reached or doesn't ask to sign in."""
        if not server.url:
            raise McpServerError(f"{server.name} runs on this computer: there's nothing to sign in to.")
        if previous := self._signing_in.pop(server.name, None):
            previous.cancel()
        started = await sign_in.start(server, self._auth, redirect_uri, self._factory)
        self._signing_in[server.name] = started
        return started

    async def finish_sign_in(self, started: McpSignIn, code: str) -> None:
        """Raises SignInError. The server connects again with the new sign-in."""
        if self._signing_in.get(started.server) is started:
            del self._signing_in[started.server]
        await started.finish(code)
        await self.restart(started.server)

    async def _apply(self, server: McpServer) -> None:
        running = self._running.get(server.name)
        if running is not None and _same_connection(running.connection.server, server):
            running.connection.server = server
            return
        if running is not None:
            await self._stop(server.name)
        await self._start(server)

    async def _start(self, server: McpServer) -> None:
        on_demand = await self._on_demand(server)
        connection = McpConnection(
            server,
            self._changed,
            self._health,
            self._factory,
            self._auth,
            self._prepare,
            on_demand,
            self._work_finished,
        )
        stop = asyncio.Event()
        self._running[server.name] = _Running(connection, stop, asyncio.create_task(connection.run(stop)))

    async def _on_demand(self, server: McpServer) -> OnDemand | None:
        """Local servers run on demand: a remote one costs nothing here while connected."""
        if not server.command:
            return None
        save = partial(tool_cache.save, self._store, server.name)
        return OnDemand(await tool_cache.load(self._store, server.name), save)

    async def _work_finished(self, server: McpServer, finished: WorkFinished) -> None:
        if self._background is not None:
            await self._background.deliver(finished.origin, background.ended(server.name, finished))

    async def _prepare(self, server: McpServer) -> None:
        if self._environments is not None:
            await self._environments.ensure(server.name, server.command)

    async def _stop(self, name: str) -> None:
        running = self._running.pop(name)
        running.stop.set()
        with contextlib.suppress(Exception):
            await running.task

    async def _stop_all(self) -> None:
        for name in list(self._running):
            await self._stop(name)
        self._changed()

    def _changed(self) -> None:
        self._tools = self._collect()
        self._bus.publish("mcp")

    def _collect(self) -> dict[str, McpTool]:
        tools: dict[str, McpTool] = {}
        for running in self._running.values():
            connection = running.connection
            for tool in connection.state.tools:
                if connection.server.selects(tool.name):
                    _add(tools, connection, tool, self._media)
        return tools


def _add(tools: dict[str, McpTool], connection: McpConnection, tool: Tool, media: ToolMedia) -> None:
    name = tool_name(connection.server.name, tool.name)
    if len(name) > MAX_TOOL_NAME or name in tools:
        logger.warning("MCP tool %s left out: its name is too long or taken by another tool", name)
        return
    tools[name] = McpTool(
        name=name,
        description=strip_hidden(tool.description or tool.title or tool.name),
        args_schema=json.loads(strip_hidden(json.dumps(tool.input_schema, ensure_ascii=False))),
        connection=connection,
        media=media,
        remote_name=tool.name,
        read_only=_read_only(tool),
        trusted=connection.server.trusted,
    )


def _definition(tool: McpTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description, "parameters": tool.args_schema},
    }


def _info(server: McpServer, tool: Tool) -> McpToolInfo:
    description = strip_hidden(tool.description or "")
    return McpToolInfo(tool.name, description, _read_only(tool), server.selects(tool.name))


def _read_only(tool: Tool) -> bool:
    return bool(tool.annotations and tool.annotations.read_only_hint)


def _same_connection(old: McpServer, new: McpServer) -> bool:
    return all(getattr(old, f) == getattr(new, f) for f in _CONNECTION_FIELDS)


async def _ignore(message: IncomingMessage) -> None:
    pass
