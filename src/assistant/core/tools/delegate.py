"""The delegate tool: hands a task to a subagent (core/subagent.py), which works on it with a fresh context and returns
only its answer to the model; the steps it took go with the answer for history (core/subagent_steps.py). In
scheduled jobs too: an approval inside the subagent pauses the run like any other, so it follows the job's
forwarding rules (core/approvals.py).

With `background`, the subagent is sent off to work while the conversation goes on (core/background_subagents/): the
call returns at once, and its answer comes back to the conversation when it ends. Where nobody would hear that end
(a scheduled job's run, which ends with its reply), the call waits for it as without."""

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core import subagent_steps
from assistant.core.context import BackgroundSubagentStarts, Context, thread_of
from assistant.core.mcp.subagents import UnknownSubagentError
from assistant.core.tools.registry import register


@register("subagents")
@tool
async def delegate(
    task: str, runtime: ToolRuntime[Context], agent: str = "", background: bool = False
) -> str | ToolMessage:
    """Hand a self-contained task to a subagent, for work whose output you only need a summary of (research
    across many pages, digging through files or logs), and get back its answer. It knows nothing of this
    conversation and can't message, send, schedule or save. `agent`: a named subagent listed under Subagents,
    for a task it's made for; empty for a general one. Calls in one reply run in parallel. How to write
    `task`: the writing-briefs skill.

    `background`: false (the default) waits for the answer, for a quick job you need before replying; it stops
    after a set number of steps. True sends it off to work in the background with no step limit and returns at
    once: for long work, so the user can go on talking meanwhile. Its answer comes back to this conversation when
    it ends, and you're asked to follow it up then; the user sees its progress in the app."""
    context = runtime.context
    if context.subagents is None:
        return "Not delegated: subagents aren't available here."
    plugins = runtime.state.get("loaded_plugins", [])
    try:
        if background and context.background is not None:
            return await _sent_off(task, runtime, context.background, plugins, agent.strip())
        call_id = runtime.tool_call_id or ""
        answer = await context.subagents.run(task, context, call_id, plugins, agent.strip())
    except UnknownSubagentError as e:
        return f"Not delegated: {e}"
    return subagent_steps.result(answer, call_id, "delegate")


async def _sent_off(
    task: str, runtime: ToolRuntime[Context], starts: BackgroundSubagentStarts, plugins: list[str], agent: str
) -> str:
    context, thread_id = runtime.context, thread_of(runtime.config)
    subagent_id = await starts.start(task, context.user_id, thread_id, context.channel, plugins, agent)
    return (
        f"Sent off as background subagent {subagent_id}. Its answer comes back to this conversation when it ends: "
        "don't wait for it, and don't do its task yourself meanwhile."
    )
