"""MCP servers as text, and parsing what the user types for them, for the /mcp screens."""

import shlex

from assistant.core.agent import McpServerStatus, McpToolInfo
from assistant_terminal.health_text import failures_line, label
from assistant_terminal.i18n import t, translatable

_STATUS = {
    "connected": translatable("connected"),
    "connecting": translatable("connecting…"),
    "failed": translatable("can't connect"),
    "needs_sign_in": translatable("needs you to sign in"),
    "idle": translatable("starts when used"),
    "off": translatable("off"),
}


def shown(servers: list[McpServerStatus]) -> list[McpServerStatus]:
    """The servers /mcp lists: a plugin without tools (a chat channel, an email provider) is set up in
    /plugins. Slack has tools as well as its channel, so it stays."""
    return [s for s in servers if s.transport != "none"]


def status(server: McpServerStatus) -> str:
    return t(_STATUS[server.status]) if server.status in _STATUS else server.status


def summary(server: McpServerStatus) -> str:
    """One line for the list: the name and whether it's working."""
    origin = " · " + t("plugin {plugin}", plugin=server.plugin) if server.plugin else ""
    return f"{server.name} · {status(server)}{origin}{label(server.failing)}"


def describe(server: McpServerStatus) -> str:
    """Markdown: how it's reached, its state, trust, and secrets by name only."""
    where = f"`{shlex.join([server.command, *server.args])}`" if server.command else server.url
    reached = t("Local command: {where}", where=where) if server.command else t("Remote: {where}", where=where)
    lines = [f"## {server.name}", reached]
    lines.append(t("Status: {status}", status=status(server)) + (f" ({server.error})" if server.error else ""))
    if failures := failures_line(server.failures, server.failure, server.failed_at):
        lines.append(failures)
    lines.append(_trust(server.trusted, any(tool.asks_first for tool in server.tools)))
    lines.append(
        t("Added by: the {plugin} plugin", plugin=server.plugin) if server.plugin else t("Added by: you, by hand")
    )
    if server.plugin:
        lines.append(t("To remove it, remove the {plugin} plugin in /plugins.", plugin=server.plugin))
    if server.source:
        lines.append(t("Installed from {source}", source=server.source))
    if server.page:
        lines.append(t("It has a page: open it from the sidebar of the web app."))
    if server.channel:
        lines.append(t("It's also a chat channel: set it up in /plugins."))
    secrets = server.env_keys if server.command else server.header_keys
    if secrets:
        names = ", ".join(secrets)
        lines.append(
            t("Env: {names} (values hidden)", names=names)
            if server.command
            else t("Headers: {names} (values hidden)", names=names)
        )
    if server.tools:
        lines.append(
            t(
                "Tools the assistant gets are checked. Read-only tools are marked (read-only), "
                "tools that always ask for your approval (asks first)."
            )
        )
    return "\n\n".join(lines)


def tool_label(tool: McpToolInfo) -> str:
    marker = " " + t("(read-only)") if tool.read_only else " " + t("(asks first)") if tool.asks_first else ""
    return f"{tool.name}{marker}: {tool.description.splitlines()[0] if tool.description else ''}"


def selection(tools: list[McpToolInfo], selected: set[str]) -> tuple[list[str], list[str]]:
    """The include and exclude lists for the checked tools. All checked: neither, so tools the
    server adds later are offered too. None checked: exclude everything (an empty include means all)."""
    names = [tool.name for tool in tools]
    if set(names) <= selected:
        return [], []
    chosen = [n for n in names if n in selected]
    return (chosen, []) if chosen else ([], ["*"])


def parse_pairs(text: str, separator: str) -> dict[str, str]:
    """`KEY=value` (env) or `Name: value` (headers) lines. Raises ValueError for a line without one."""
    pairs: dict[str, str] = {}
    for line in filter(None, (raw.strip() for raw in text.splitlines())):
        key, found, value = line.partition(separator)
        if not found or not key.strip():
            raise ValueError(t("Expected {example} on each line, got: {line}", example=_example(separator), line=line))
        pairs[key.strip()] = value.strip()
    return pairs


def parse_command(text: str) -> tuple[str, list[str]]:
    """The command and its arguments, split like a shell would. Raises ValueError."""
    parts = shlex.split(text)
    if not parts:
        raise ValueError(t("Enter the command that starts the server."))
    return parts[0], parts[1:]


def _trust(trusted: bool, some_ask_first: bool) -> str:
    if trusted and some_ask_first:
        return t("Trusted: its tools run without asking, but those marked (asks first).")
    if trusted:
        return t("Trusted: its tools run without asking.")
    return t("Not trusted: tools not marked read-only ask for your approval first.")


def _example(separator: str) -> str:
    return "KEY=value" if separator == "=" else t("Name: value")
