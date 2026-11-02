"""What a plugin's processes get of the user's when they ask for it: their ssh agent (ssh_agent.py) and their login
session (core/login_session.py). Added when a process starts, never saved with the plugin."""

from assistant.core import login_session
from assistant.core.mcp import ssh_agent
from assistant.core.mcp.servers import McpServer


def with_user(server: McpServer) -> McpServer:
    return ssh_agent.with_agent(login_session.with_session(server))
