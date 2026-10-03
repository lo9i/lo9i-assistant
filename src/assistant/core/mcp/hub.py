"""The connected MCP servers and the tools they give the agent.

The daemon runs the hub as a supervised task. The graph reads two things from it: the tool
definitions, which each epoch freezes into its state so the tool list stays byte-identical within
the epoch, and the tool to run for a call, looked up live so a tool turned off stops working at once.
"""

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from langgraph.store.base import BaseStore
from mcp.client.session import IncomingMessage
from mcp.types import Tool

from assistant.core.bus import EventBus
from assistant.core.health import Health, HealthLog
from assistant.core.hidden_text import strip_hidden
from assistant.core.mcp import servers
from assistant.core.mcp.connection import ClientFactory, McpConnection, describe, list_tools, open_client
from assistant.core.mcp.media import ToolMedia
from assistant.core.mcp.sanitize import MAX_TOOL_NAME, tool_name
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.mcp.tools import McpTool

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
class _Running:
    connection: McpConnection
    stop: asyncio.Event
    task: asyncio.Task


class McpHub:
    name = "mcp"

    def __init__(
        self,
        store: BaseStore,
        bus: EventBus,
        health: HealthLog,
        media: ToolMedia,
        factory: ClientFactory | None = None,
    ) -> None:
        self._store = store
        self._bus = bus
        self._factory = factory or open_client
        self._health = health
        self._media = media
        self._running: dict[str, _Running] = {}
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
        wanted = {s.name: s for s in await servers.load_all(self._store) if s.enabled}
        for name in [n for n in self._running if n not in wanted]:
            await self._stop(name)
        for server in wanted.values():
            await self._apply(server)
        self._changed()

    async def restart(self, name: str) -> None:
        """Connect to the server again even if its settings didn't change: its code did (an update)."""
        if self._active and name in self._running:
            await self._stop(name)
        await self.reload()

    def definitions(self) -> list[dict[str, Any]]:
        """The tool definitions for the model, in a stable order."""
        return [_definition(tool) for _, tool in sorted(self._tools.items())]

    def tool(self, name: str) -> McpTool | None:
        return self._tools.get(name)

    def unavailable(self, name: str) -> str:
        """Why a tool this epoch offers can't run now, for the model."""
        for running in self._running.values():
            connection = running.connection
            if not name.startswith(tool_name(connection.server.name, "")):
                continue
            if connection.state.status == "connected":
                return f"{name} was turned off, or {connection.server.name} no longer has it."
            state = connection.state
            reason = f"{state.status}: {state.error}" if state.error else state.status
            return f"{connection.server.name} isn't connected ({reason}). Its tools can't run now."
        return f"{name} isn't available: its MCP server was removed or turned off."

    def state(self, name: str) -> tuple[str, str, list[McpToolInfo]]:
        """A server's status (connecting, connected, failed, off), error and tools."""
        running = self._running.get(name)
        if running is None:
            return "off", "", []
        connection = running.connection
        tools = [_info(connection.server, tool) for tool in connection.state.tools]
        return connection.state.status, connection.state.error, tools

    async def health(self, name: str) -> Health:
        return await self._health.get("mcp", name)

    async def forget(self, name: str) -> None:
        """Drop the failures of a removed server, so one added later under its name starts clean."""
        await self._health.forget("mcp", name)

    async def probe(self, server: McpServer) -> list[McpToolInfo]:
        """Connect once to list a server's tools, before it's saved. Raises McpServerError."""
        servers.validate(server)
        try:
            async with asyncio.timeout(_PROBE_SECONDS), self._factory(server, _ignore) as client:
                tools = await list_tools(client)
        except Exception as e:
            reason = f"no answer within {_PROBE_SECONDS}s" if isinstance(e, TimeoutError) else describe(e)
            raise McpServerError(f"Couldn't connect to {server.name}: {reason}") from e
        return [_info(server, tool) for tool in tools]

    async def _apply(self, server: McpServer) -> None:
        running = self._running.get(server.name)
        if running is not None and _same_connection(running.connection.server, server):
            running.connection.server = server
            return
        if running is not None:
            await self._stop(server.name)
        self._start(server)

    def _start(self, server: McpServer) -> None:
        connection = McpConnection(server, self._changed, self._health, self._factory)
        stop = asyncio.Event()
        self._running[server.name] = _Running(connection, stop, asyncio.create_task(connection.run(stop)))

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
            if connection.state.status != "connected":
                continue
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
