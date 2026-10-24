"""The delegate tool: hands a task to a subagent (core/subagent.py), which works on it with a fresh
context and returns only its answer to the model; the steps it took go with the answer for history
(core/subagent_steps.py)."""

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core import subagent_steps
from assistant.core.context import Context
from assistant.core.tools.registry import register


@register("subagents")
@tool
async def delegate(task: str, runtime: ToolRuntime[Context]) -> str | ToolMessage:
    """Hand a self-contained task to a subagent and get back its answer. It starts with nothing of this
    conversation, so `task` must say everything it needs: the goal, names, paths, what to return. It can
    run commands, search the web, read email and memory and use skills, but can't message the user,
    send, schedule or save anything. Use it for work that would fill this conversation with output you
    only need a summary of (research across many pages, digging through files or logs). Several calls
    in one reply run in parallel."""
    context = runtime.context
    if context.unattended:
        return "Not delegated: subagents don't run in scheduled jobs. Do the task yourself."
    if context.subagents is None:
        return "Not delegated: subagents aren't available here."
    call_id = runtime.tool_call_id or ""
    return subagent_steps.result(await context.subagents.run(task, context, call_id), call_id, "delegate")
