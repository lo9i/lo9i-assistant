"""Where an MCP server installed from a repository lives: its code, which updates replace, and its
data, which they keep."""

from pathlib import Path

from assistant.core.config import settings

# The socket a server's page listens on, in its data folder: only the user can open that folder.
PAGE_SOCKET = "page.sock"


def code(name: str) -> Path:
    return Path(settings.mcp_dir).expanduser() / name


def data(name: str) -> Path:
    return Path(settings.mcp_data_dir).expanduser() / name


def page_socket(name: str) -> Path:
    return data(name) / PAGE_SOCKET
