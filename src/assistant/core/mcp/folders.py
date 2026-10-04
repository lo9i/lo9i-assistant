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


def library(name: str) -> Path:
    """A shared library plugins use (`libraries:` in server.yaml). It sits two levels above a plugin's
    folder, as `lib/` does above `mcp/<name>` in the repository, so a plugin's uv path dependency on
    `../../lib/<name>` works in both places."""
    return Path(settings.mcp_dir).expanduser().parent / "lib" / name


def page_socket(name: str) -> Path:
    return data(name) / PAGE_SOCKET
