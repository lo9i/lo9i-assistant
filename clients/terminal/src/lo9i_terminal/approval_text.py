"""An approval request in words, for the approval screen and the plain REPL. An MCP tool's call comes with what it
does and what it's given (`call`, the daemon's core/mcp/described.py), so the user reads that before the JSON;
any other request shows its tool, its reason and its command."""

from typing import Any, cast

from lo9i_terminal.i18n import t, translatable

_UNTRUSTED = translatable("{server} isn't trusted, and this tool can change things.")
_ASKS_FIRST = translatable("{server} asks before each use of this tool.")


def call_of(request: dict[str, Any]) -> dict[str, Any] | None:
    call = request.get("call")
    return cast(dict[str, Any], call) if isinstance(call, dict) else None


def approval_title(request: dict[str, Any]) -> str:
    call = call_of(request)
    if call is None:
        return t("Approve {tool}?", tool=request.get("tool"))
    return t("Approve {tool} from {server}?", tool=call.get("tool"), server=call.get("server"))


def approval_why(request: dict[str, Any]) -> str:
    call = call_of(request)
    if call is None:
        return str(request.get("reason") or "")
    return t(_ASKS_FIRST if call.get("why") == "asks_first" else _UNTRUSTED, server=call.get("server"))


def call_lines(call: dict[str, Any]) -> list[str]:
    """What it does, then each argument it's given with what it is, or that it's given none."""
    does = [str(call["does"])] if call.get("does") else []
    arguments = [_argument(a) for a in call.get("arguments") or []]
    return [*does, *(arguments or [t("No arguments: it runs with its defaults.")])]


def _argument(argument: dict[str, str]) -> str:
    about = f" ({argument['about']})" if argument.get("about") else ""
    return f"• {argument.get('name')}: {argument.get('value')}{about}"
