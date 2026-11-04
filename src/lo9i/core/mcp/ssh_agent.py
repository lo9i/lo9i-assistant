"""The user's ssh agent, for plugins that declare they need it (`ssh_agent: true` in their server.yaml): their
processes (the MCP server, the page) get `SSH_AUTH_SOCK`, which MCP's default environment leaves out, so keys
held only by the agent (a passphrase key not in the macOS keychain) work for their ssh. Added when a process
starts, never saved with the plugin. The daemon's own agent; one started from boot (a LaunchDaemon) has none, so
its plugins get the login session's instead, which the session helper links while the user is logged in
(core/login_session.py)."""

import os
from dataclasses import replace

from lo9i.core import login_session
from lo9i.core.i18n import said
from lo9i.core.mcp.servers import McpServer

ENV = "SSH_AUTH_SOCK"


def parse(value: object) -> bool:
    """Raises ValueError for anything but true or false."""
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError(said("its ssh_agent must be true or false"))
    return value


def with_agent(server: McpServer) -> McpServer:
    """The server with the agent's socket in its env when it asks for it and the daemon has one."""
    socket = str(login_session.ssh_agent_link()) if login_session.from_boot() else os.environ.get(ENV, "")
    return replace(server, env={**server.env, ENV: socket}) if server.ssh_agent and socket else server
