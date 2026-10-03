"""Names for MCP tools that model providers accept."""

import re

_INVALID_NAME = re.compile(r"[^A-Za-z0-9_]")
# Model providers reject longer tool names.
MAX_TOOL_NAME = 64
MCP_PREFIX = "mcp__"


def tool_name(server: str, tool: str) -> str:
    """The name the model sees: mcp__<server>__<tool>, with anything but letters, digits and _ as _."""
    return f"{MCP_PREFIX}{_INVALID_NAME.sub('_', server)}__{_INVALID_NAME.sub('_', tool)}"
