"""The SSH hosts a plugin keeps (core/mcp/ssh_hosts.py), for moving lo9i to one: listed without how to sign in, one's
config and password asked for by name, the agent never given the tool, and a plugin that fails left out."""

import json
from typing import Any

from langgraph.store.memory import InMemoryStore
from mcp.types import CallToolResult, TextContent

from lo9i.core.mcp import servers
from lo9i.core.mcp.servers import McpServer
from lo9i.core.mcp.ssh_hosts import HostConnection, SavedHost, SshHosts

HOSTS = McpServer(name="hosts", command="hosts-mcp", ssh_hosts_tool="ssh_hosts")
BROKEN = McpServer(name="broken", command="broken-mcp", ssh_hosts_tool="ssh_hosts")


class _Calls:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> CallToolResult:
        self.calls.append((server, arguments))
        if server == "broken":
            return CallToolResult(content=[TextContent(type="text", text="locked")], is_error=True)
        answer = (
            {"config": "Host pi\n  HostName pi.local\n", "password": "secret"}
            if arguments
            else {"hosts": [{"name": "pi", "address": "me@pi.local"}]}
        )
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(answer))])


async def test_hosts_are_listed_without_secrets_and_one_is_signed_in_to_by_name():
    store = InMemoryStore()
    for server in (BROKEN, HOSTS):
        await servers.save(store, server)
    calls = _Calls()
    hosts = SshHosts(store, calls)

    assert await hosts.every() == [SavedHost("hosts", "pi", "me@pi.local")]
    assert await hosts.connection("hosts", "pi") == HostConnection("Host pi\n  HostName pi.local\n", "secret")
    assert ("hosts", {"name": "pi"}) in calls.calls
    assert not HOSTS.selects("ssh_hosts") and HOSTS.only_lo9i_calls("ssh_hosts")
