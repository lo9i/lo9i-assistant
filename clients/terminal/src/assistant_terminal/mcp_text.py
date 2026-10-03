"""MCP servers as text, and parsing what the user types for them, for the /mcp screens."""

import shlex

from assistant.core.agent import McpServerStatus, McpToolInfo
from assistant_terminal.health_text import failures_line, label

_STATUS = {"connected": "connected", "connecting": "connecting…", "failed": "can't connect", "off": "off"}


def summary(server: McpServerStatus) -> str:
    """One line for the list: the name and whether it's working."""
    return f"{server.name} · {_STATUS.get(server.status, server.status)}{label(server.failing)}"


def describe(server: McpServerStatus) -> str:
    """Markdown: how it's reached, its state, trust, and secrets by name only."""
    where = f"`{shlex.join([server.command, *server.args])}`" if server.command else server.url
    lines = [f"## {server.name}", f"{'Local command' if server.command else 'Remote'}: {where}"]
    lines.append(
        f"Status: {_STATUS.get(server.status, server.status)}" + (f" ({server.error})" if server.error else "")
    )
    if failures := failures_line(server.failures, server.failure, server.failed_at):
        lines.append(failures)
    lines.append(_trust(server.trusted))
    if server.source:
        lines.append(f"Installed from {server.source}")
    if server.page:
        lines.append("It has a page: open it from the sidebar of the web app.")
    secrets = server.env_keys if server.command else server.header_keys
    if secrets:
        lines.append(f"{'Env' if server.command else 'Headers'}: {', '.join(secrets)} (values hidden)")
    if server.tools:
        lines.append("Tools the assistant gets are checked. Read-only tools are marked (read-only).")
    return "\n\n".join(lines)


def tool_label(tool: McpToolInfo) -> str:
    marker = " (read-only)" if tool.read_only else ""
    return f"{tool.name}{marker}: {tool.description.splitlines()[0] if tool.description else ''}"


def selection(tools: list[McpToolInfo], selected: set[str]) -> tuple[list[str], list[str]]:
    """The include and exclude lists for the checked tools. All checked: neither, so tools the
    server adds later are offered too. None checked: exclude everything (an empty include means all)."""
    names = [t.name for t in tools]
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
            raise ValueError(f"Expected {_example(separator)} on each line, got: {line}")
        pairs[key.strip()] = value.strip()
    return pairs


def parse_command(text: str) -> tuple[str, list[str]]:
    """The command and its arguments, split like a shell would. Raises ValueError."""
    parts = shlex.split(text)
    if not parts:
        raise ValueError("Enter the command that starts the server.")
    return parts[0], parts[1:]


def _trust(trusted: bool) -> str:
    if trusted:
        return "Trusted: its tools run without asking."
    return "Not trusted: tools not marked read-only ask for your approval first."


def _example(separator: str) -> str:
    return "KEY=value" if separator == "=" else "Name: value"
