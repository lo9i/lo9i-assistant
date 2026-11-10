"""SSH hosts a plugin keeps, for moving lo9i to one of them (core/migration/): `ssh_hosts:` in its server.yaml names a
read-only tool of its MCP server that lo9i calls itself, never through the model. The agent never gets it, since it
gives each host's password; a daemon that didn't know the section would, so it needs format 8
(core/repositories/formats.py).

    ssh_hosts:
      tool: ssh_hosts              # called with {}: the hosts, {"hosts": [{"name": "pi", "address": "me@pi.local"}]};
                                   # with {"name": "pi"}: how to connect to it, {"config": "...", "password": "..."}

`config` is an OpenSSH client configuration with a `Host` entry named after the host (and any it jumps through),
which lo9i reads for that one connection and never writes anywhere; `password` is "" for none. A key is only ever
named by its file's path there: lo9i reads no key it isn't pointed to and copies none."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from langgraph.store.base import BaseStore
from mcp.types import CallToolResult
from pydantic import BaseModel

from lo9i.core.i18n import said
from lo9i.core.mcp import servers
from lo9i.core.mcp.servers import McpServer

logger = logging.getLogger(__name__)

_PARTS = said("its ssh_hosts section must name a tool")


class SshHostsError(Exception):
    """A plugin's host can't be read. The text says why."""


@dataclass(frozen=True)
class SavedHost:
    plugin: str
    name: str
    # user@hostname:port, for the apps to show.
    address: str


@dataclass(frozen=True)
class HostConnection:
    config: str
    password: str


class _Listed(BaseModel):
    name: str
    address: str = ""


class _Hosts(BaseModel):
    hosts: list[_Listed] = []


class _Connection(BaseModel):
    config: str
    password: str = ""


class ToolCalls(Protocol):
    """Calls a plugin's tool directly (core/mcp/hub.py)."""

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> CallToolResult: ...


def parse(value: object) -> dict[str, Any]:
    """The `ssh_hosts:` section as the server's field; none without one. Raises ValueError for one that can't be
    used."""
    if value is None:
        return {}
    tool = str(value.get("tool") or "").strip() if isinstance(value, dict) else ""
    if not tool:
        raise ValueError(_PARTS)
    return {"ssh_hosts_tool": tool}


class SshHosts:
    """The hosts every plugin on keeps, and how to connect to one."""

    def __init__(self, store: BaseStore, calls: ToolCalls) -> None:
        self._store = store
        self._calls = calls

    async def every(self) -> list[SavedHost]:
        """The hosts, plugin by plugin; one that fails is left out, and logged."""
        found: list[SavedHost] = []
        for server in await self._plugins():
            try:
                hosts = _Hosts.model_validate(await self._answer(server, {}))
            except (SshHostsError, ValueError) as e:
                logger.info("%s couldn't list its hosts: %s", server.name, e)
                continue
            found += [SavedHost(server.name, h.name, h.address) for h in hosts.hosts]
        return found

    async def connection(self, plugin: str, name: str) -> HostConnection:
        """Raises SshHostsError: the plugin is off or keeps no hosts, or doesn't have this one."""
        server = next((s for s in await self._plugins() if s.name == plugin), None)
        if server is None:
            raise SshHostsError(said("{plugin} keeps no hosts, or is off.", plugin=plugin))
        try:
            found = _Connection.model_validate(await self._answer(server, {"name": name}))
        except ValueError as e:
            raise SshHostsError(
                said("{plugin} gave {name} in a form lo9i can't read.", plugin=plugin, name=name)
            ) from e
        return HostConnection(found.config, found.password)

    async def _plugins(self) -> list[McpServer]:
        return [s for s in await servers.load_all(self._store) if s.enabled and s.ssh_hosts_tool]

    async def _answer(self, server: McpServer, arguments: dict[str, Any]) -> Any:
        try:
            result = await self._calls.call(server.name, server.ssh_hosts_tool, arguments)
        except Exception as e:
            raise SshHostsError(said("{plugin} couldn't be asked: {error}", plugin=server.name, error=e)) from e
        if result.is_error:
            raise SshHostsError(_text(result))
        return result.structured_content if result.structured_content is not None else json.loads(_text(result))


def _text(result: CallToolResult) -> str:
    return "\n".join(block.text for block in result.content if block.type == "text")
