"""An installed plugin's settings: the values its fields were given, changed after it's installed (its details in
Plugins, in both apps). The fields are those its installed server.yaml declares (install.installed_fields); the rest
of its env or headers, what its server.yaml sets, stays as installed.

What the apps get back is a field's value only when it isn't secret; a secret one says only whether it's set. A
secret given empty keeps the saved one, unless the user clears it; any other field given empty is emptied."""

from dataclasses import dataclass, replace

from assistant.core.mcp.install import ServerField
from assistant.core.mcp.servers import McpServer, McpServerError


@dataclass
class PluginFieldValue:
    """A field as the apps show it in the plugin's settings."""

    key: str
    label: str
    secret: bool = False
    help: str = ""
    optional: bool = False
    # Its value; "" for a secret one, which never leaves the daemon.
    value: str = ""
    # It has a value: for a secret one, the only thing said about it.
    set: bool = False


@dataclass
class PluginSettings:
    name: str
    fields: list[PluginFieldValue]
    # It checks the values before they're saved (core/mcp/checks.py), for the apps to say so while it runs.
    check: bool = False


@dataclass(frozen=True)
class SettingsChange:
    """The server with the values to save, and the keys emptied on purpose, which keys.save doesn't keep."""

    server: McpServer
    cleared: frozenset[str]


def shown(server: McpServer, fields: list[ServerField]) -> PluginSettings:
    """`server` with its keys filled in (keys.fill)."""
    values = _values(server)
    return PluginSettings(
        server.name,
        [_shown(f, values.get(f.key, "")) for f in fields],
        bool(server.check_command or server.check_tool),
    )


def changed(server: McpServer, fields: list[ServerField], values: dict[str, str], clear: list[str]) -> SettingsChange:
    """`server` (keys filled in) with the values given; a field not given keeps its value, and `clear` empties
    secret ones. Raises McpServerError for a field it doesn't have or a required one left empty."""
    by_key = {f.key: f for f in fields}
    if unknown := sorted({*values, *clear} - set(by_key)):
        raise McpServerError(f"{server.name} has no setting {', '.join(unknown)}.")
    current = _values(server)
    new = {k: _new(by_key[k], current.get(k, ""), v.strip(), k in clear) for k, v in values.items()}
    new |= {k: "" for k in clear if k not in new}
    if missing := next((f for f in fields if not f.optional and not {**current, **new}.get(f.key, "")), None):
        raise McpServerError(f"{server.name} needs {missing.label}.")
    cleared = frozenset(k for k, v in new.items() if not v)
    target = "headers" if server.url else "env"
    return SettingsChange(replace(server, **{target: {**getattr(server, target), **new}}), cleared)


def _new(f: ServerField, current: str, given: str, clear: bool) -> str:
    """A secret given empty is kept, unless cleared."""
    if f.secret and not given and not clear:
        return current
    return given


def _values(server: McpServer) -> dict[str, str]:
    return server.headers if server.url else server.env


def _shown(f: ServerField, value: str) -> PluginFieldValue:
    return PluginFieldValue(f.key, f.label, f.secret, f.help, f.optional, "" if f.secret else value, bool(value))
