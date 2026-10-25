"""MCP servers the user connected, one Store record each.

A server runs as a local command (stdio) or is reached at a URL (Streamable HTTP). A plugin
installed from a repository can instead, or also, be a chat channel (core/channels/): a process
the daemon runs that talks to it over HTTP; or offer email providers (core/integrations/email/),
running nothing. Its env values and headers are secrets: they are entered in a dialog, stay in the
daemon and never reach a client or the model. The user's ones (keys.py) are encrypted apart: a record
here keeps their names with empty values, so it's saved with keys.save.
"""

import fnmatch
import re
from dataclasses import asdict, dataclass, field
from typing import Any

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
    # The version of the channel protocol its process speaks (core/channels/hub.py, PROTOCOL); 1 for
    # plugins installed before it was declared.
    channel_protocol: int = 1
    # The email providers it offers (core/integrations/email/providers.py), as written in its
    # server.yaml's `email:` section. Only plugins installed from a repository have them.
    email_providers: list[dict[str, Any]] = field(default_factory=list)
    # A login of lo9i's its MCP server gets instead of one of its own (core/mcp/logins.py); "" for none.
    model_login: str = ""
    # Its processes get the user's ssh agent (core/mcp/ssh_agent.py).
    ssh_agent: bool = False
    # A coding agent it brings (docs/agent-plugins.md): the apps' command that hands a conversation to it
    # (/claude), its name, and the worker the daemon runs for each of its tasks (core/agent_tasks/).
    agent_command: str = ""
    agent_name: str = ""
    agent_worker: str = ""
    agent_args: list[str] = field(default_factory=list)
    # Which env or header values are the user's keys (keys.py): its fields, for a plugin installed
    # from a repository. One added by hand has all of them as keys.
    keys: list[str] = field(default_factory=list)
    # What the apps show beside it, as its plugin declared it (core/repositories/icons.py's PluginIcon);
    # empty for one added by hand or installed before icons.
    icon: dict[str, Any] = field(default_factory=dict)

    @property
    def transport(self) -> str:
        """stdio or http for an MCP server; none for a plugin without MCP tools (a chat channel, an
        email provider)."""
        if self.command:
            return "stdio"
        return "http" if self.url else "none"

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
    if not (server.command.strip() or server.url.strip() or server.channel_command.strip() or _runs_nothing(server)):
        raise McpServerError("Give either a command (local server) or a URL (remote server).")
    if server.url and not server.url.startswith(("https://", "http://")):
        raise McpServerError("The URL must start with https:// or http://.")


def _runs_nothing(server: McpServer) -> bool:
    """A plugin with no process of its own: email presets, or an agent whose worker runs per task."""
    return bool(server.email_providers or server.agent_worker.strip())


async def load_all(store: BaseStore) -> list[McpServer]:
    items = await store.asearch(_NAMESPACE, limit=1000)
    return sorted((_from_record(item.value) for item in items), key=lambda s: s.name)


async def load(store: BaseStore, name: str) -> McpServer:
    """Raises McpServerError for an unknown server."""
    item = await store.aget(_NAMESPACE, name)
    if item is None:
        raise McpServerError(f"No MCP server named {name}.")
    return _from_record(item.value)


def _from_record(value: dict[str, Any]) -> McpServer:
    """Settings a record kept from an older version (an agent's `agent_tool`) are left out: the plugin
    is updated to the current format to use them."""
    known = McpServer.__dataclass_fields__
    return McpServer(**{k: v for k, v in value.items() if k in known})


async def save(store: BaseStore, server: McpServer) -> None:
    validate(server)
    await store.aput(_NAMESPACE, server.name, asdict(server))


async def set_icon(store: BaseStore, name: str, icon: dict[str, Any]) -> None:
    """The record's icon alone: its keys, kept apart (keys.py), and every other setting stay as saved. Raises
    McpServerError for an unknown server."""
    item = await store.aget(_NAMESPACE, name)
    if item is None:
        raise McpServerError(f"No MCP server named {name}.")
    await store.aput(_NAMESPACE, name, {**item.value, "icon": icon})


async def remove(store: BaseStore, name: str) -> None:
    await load(store, name)
    await store.adelete(_NAMESPACE, name)


def _matches(tool: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(tool, pattern) for pattern in patterns)
