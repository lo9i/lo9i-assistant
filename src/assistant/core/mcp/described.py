"""What an MCP tool call will do, in words, for the approval it waits for: the tool's own description and each
argument it's given with that argument's description, beside the call's JSON. The apps write the rest in their
language; the descriptions are the server's own text."""

import json
from typing import Any

from langchain_core.tools import BaseTool

# Why it asks: its server isn't trusted, or its plugin asks before each call of it (McpServer.approve).
UNTRUSTED, ASKS_FIRST = "untrusted", "asks_first"
_DOES_MAX = 400
_VALUE_MAX = 300


def described(tool: BaseTool, server: str, remote_name: str, arguments: dict[str, Any], why: str) -> dict[str, Any]:
    """The call as the approval dialogs show it. An argument given as null is left out, as the tool takes it."""
    properties = tool.args_schema.get("properties", {}) if isinstance(tool.args_schema, dict) else {}
    return {
        "server": server,
        "tool": remote_name,
        "does": _does(tool.description, remote_name),
        "arguments": [
            _argument(name, value, properties.get(name)) for name, value in arguments.items() if value is not None
        ],
        "why": why,
    }


def _does(description: str, remote_name: str) -> str:
    """Its first paragraph, which says what it does; nothing when the server gave it no description."""
    first = " ".join(description.strip().split("\n\n")[0].split())
    return "" if first == remote_name else _cut(first, _DOES_MAX)


def _argument(name: str, value: Any, schema: Any) -> dict[str, str]:
    about = schema.get("description", "") if isinstance(schema, dict) else ""
    shown = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return {"name": name, "about": " ".join(str(about).split()), "value": _cut(shown, _VALUE_MAX)}


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"
