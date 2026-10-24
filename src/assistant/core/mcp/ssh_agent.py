"""The user's ssh agent, for plugins that declare they need it (`ssh_agent: true` in their server.yaml): their
processes (the MCP server, the page) get `SSH_AUTH_SOCK`, which MCP's default environment leaves out, so keys
held only by the agent (a passphrase key not in the macOS keychain) work for their ssh. Added when a process
starts, never saved with the plugin. Only the daemon's own agent: one started from boot (a LaunchDaemon) has
none, so nothing is added there."""

import os
from dataclasses import replace

from assistant.core.mcp.servers import McpServer

ENV = "SSH_AUTH_SOCK"


def parse(value: object) -> bool:
    """Raises ValueError for anything but true or false."""
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError("its ssh_agent must be true or false")
    return value


def with_agent(server: McpServer) -> McpServer:
    """The server with the agent's socket in its env when it asks for it and the daemon has one."""
    socket = os.environ.get(ENV, "")
    return replace(server, env={**server.env, ENV: socket}) if server.ssh_agent and socket else server
