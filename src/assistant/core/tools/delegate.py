"""The delegate tool: hands a task to a subagent (core/subagent.py), which works on it with a fresh
context and returns only its answer to the model; the steps it took go with the answer for history
(core/subagent_steps.py). In scheduled jobs too: an approval inside the subagent pauses the run like any
other, so it follows the job's forwarding rules (core/approvals.py)."""

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core import subagent_steps
from assistant.core.context import Context
from assistant.core.mcp.subagents import UnknownSubagentError
from assistant.core.tools.registry import register


@register("subagents")
@tool
async def delegate(task: str, runtime: ToolRuntime[Context], agent: str = "") -> str | ToolMessage:
    """Hand a self-contained task to a subagent, for work whose output you only need a summary of (research
    across many pages, digging through files or logs), and get back its answer. It knows nothing of this
    conversation and can't message, send, schedule or save. `agent`: a named subagent listed under Subagents,
    for a task it's made for; empty for a general one. Calls in one reply run in parallel. How to write
    `task`: the writing-briefs skill."""
    context = runtime.context
    if context.subagents is None:
        return "Not delegated: subagents aren't available here."
    call_id = runtime.tool_call_id or ""
    plugins = runtime.state.get("loaded_plugins", [])
    try:
        answer = await context.subagents.run(task, context, call_id, plugins, agent.strip())
    except UnknownSubagentError as e:
        return f"Not delegated: {e}"
    return subagent_steps.result(answer, call_id, "delegate")
