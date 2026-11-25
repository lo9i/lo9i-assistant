"""What a run that read text from outside (core/untrusted.py) may do: while it's tainted, a tool that changes
something (bash, sending, scheduling, memory, an MCP tool that doesn't only read) asks the user first (`guarded`),
through the approvals every other tool uses (core/tools/approval.py), so a scheduled run's go to the chat channels.
Tools that only read, or ask the user anyway, stay free (core/tools/registry.py's `free_when_tainted`), and the next
user message starts clean: the user saw the reply and chose what to say next. A subagent sent from a tainted run
starts tainted (core/subagent.py)."""

import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt.tool_node import AsyncToolCallWrapper, ToolCallRequest

from lo9i.core.context import Context
from lo9i.core.tools.approval import approved, ask
from lo9i.core.tools.registry import is_free_when_tainted
from lo9i.core.untrusted import taint_source


@runtime_checkable
class TaintAware(Protocol):
    """A tool whose call may or may not change things depending on its arguments (an MCP tool)."""

    def asks_when_tainted(self, arguments: dict[str, Any]) -> bool: ...


def asks_when_tainted(tool: BaseTool, arguments: dict[str, Any]) -> bool:
    if isinstance(tool, TaintAware):
        return tool.asks_when_tainted(arguments)
    return not is_free_when_tainted(tool)


def guarded(execute_call: AsyncToolCallWrapper) -> AsyncToolCallWrapper:
    """Wraps a tool node's calls (`execute_call` finds the tool, core/graph.py::mcp_calls) so that, in a tainted run,
    one that changes things asks the user first. Approved, the tool's own approval isn't asked again."""

    async def _wrap(request: ToolCallRequest, execute: Callable[[ToolCallRequest], Awaitable[Any]]) -> Any:
        return await execute_call(request, lambda found: _gated(found, execute))

    return _wrap


async def _gated(request: ToolCallRequest, execute: Callable[[ToolCallRequest], Awaitable[Any]]) -> Any:
    call, tool = request.tool_call, request.tool
    if tool is None or not asks_when_tainted(tool, call["args"]) or not (source := taint_source(request.state)):
        return await execute(request)
    context = request.runtime.context
    if not isinstance(context, Context):
        raise RuntimeError("A tool was called outside a run.")
    if rejection := ask(_request(call["name"], call["args"], source), context):
        return ToolMessage(rejection, tool_call_id=call["id"], name=call["name"], status="error")
    with approved():
        return await execute(request)


def _request(name: str, arguments: dict[str, Any], source: str) -> dict[str, Any]:
    command = arguments.get("command") if name == "bash" else None
    shown = command if isinstance(command, str) else json.dumps(arguments, indent=2, ensure_ascii=False)
    reason = (
        f"this reply read content from outside ({source}), which may carry instructions that aren't yours: "
        "check this is something you asked for"
    )
    return {"tool": name, "command": shown, "reason": reason}
