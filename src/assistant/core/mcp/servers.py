"""MCP servers the user connected, one Store record each.

A server runs as a local command (stdio) or is reached at a URL (Streamable HTTP). A plugin
installed from a repository can instead, or also, be a chat channel (core/channels/): a process
the daemon runs that talks to it over HTTP. Its env values and headers are secrets: they are
entered in a dialog, stay in the daemon and never reach a client or the model.
"""

import fnmatch
import re
from dataclasses import asdict, dataclass, field

from langgraph.store.base import BaseStore

_NAMESPACE = ("mcp_servers",)
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,23}$")


class McpServerError(Exception):
    """A server's settings are invalid, or it doesn't exist. The text says which."""


@dataclass
class McpServer:
    name: str
    # Exactly one of command (stdio) and url (HTTP) is set.
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    # On an untrusted server, every tool not marked read-only needs approval.
    trusted: bool = False
    # Tool names or globs. When include is set, only those tools are used, and exclude is ignored.
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    # The repository it was installed from (core/mcp/install.py); "" when added by hand.
    source: str = ""
    # A web page the server comes with, run as its own process with the server's env and shown in the
    # web app (core/mcp/pages.py). Only servers installed from a repository have one.
    page_command: str = ""
    page_args: list[str] = field(default_factory=list)
    # A chat channel the plugin is (core/channels/processes.py), and how to write for it, for the
    # system prompt. Only plugins installed from a repository have one.
    channel_command: str = ""
    channel_args: list[str] = field(default_factory=list)
    channel_style: str = ""

    @property
    def transport(self) -> str:
        """stdio or http for an MCP server; channel for a plugin that is only a chat channel."""
        if self.command:
            return "stdio"
        return "http" if self.url else "channel"

    @property
    def is_mcp(self) -> bool:
        """It has MCP tools to connect to."""
        return bool(self.command or self.url)

    def selects(self, tool: str) -> bool:
        """Whether the agent gets this tool of the server."""
        if self.include:
            return _matches(tool, self.include)
        return not _matches(tool, self.exclude)


def validate(server: McpServer) -> None:
    """Raises McpServerError for settings that can't work."""
    if not _NAME.match(server.name):
        raise McpServerError(
            "The name must be 1-24 lowercase letters, digits, - or _, starting with a letter or digit."
        )
    if server.command.strip() and server.url.strip():
        raise McpServerError("Give either a command (local server) or a URL (remote server), not both.")
    if not (server.command.strip() or server.url.strip() or server.channel_command.strip()):
        raise McpServerError("Give either a command (local server) or a URL (remote server).")
    if server.url and not server.url.startswith(("https://", "http://")):
        raise McpServerError("The URL must start with https:// or http://.")


async def load_all(store: BaseStore) -> list[McpServer]:
    items = await store.asearch(_NAMESPACE, limit=1000)
    return sorted((McpServer(**item.value) for item in items), key=lambda s: s.name)


async def load(store: BaseStore, name: str) -> McpServer:
    """Raises McpServerError for an unknown server."""
    item = await store.aget(_NAMESPACE, name)
    if item is None:
        raise McpServerError(f"No MCP server named {name}.")
    return McpServer(**item.value)


async def save(store: BaseStore, server: McpServer) -> None:
    validate(server)
    await store.aput(_NAMESPACE, server.name, asdict(server))


async def remove(store: BaseStore, name: str) -> None:
    await load(store, name)
    await store.adelete(_NAMESPACE, name)


def _matches(tool: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(tool, pattern) for pattern in patterns)
