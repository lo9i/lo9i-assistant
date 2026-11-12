"""The delegate tool: hands a task to a subagent (core/subagent.py), which works on it with a fresh context and returns
only its answer to the model; the steps it took go with the answer for history (core/subagent_steps.py). In
scheduled jobs too: an approval inside the subagent pauses the run like any other, so it follows the job's
forwarding rules (core/approvals.py).

With `background`, the subagent is sent off to work while the conversation goes on (core/background_subagents/): the
call returns at once, and its answer comes back to the conversation when it ends. Where nobody would hear that end
(a scheduled job's run, which ends with its reply), the call waits for it as without."""

from collections.abc import Collection

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from lo9i.core import subagent_steps
from lo9i.core.context import BackgroundSubagentStarts, Context, Subagents, thread_of
from lo9i.core.mcp.subagents import UnknownSubagentError
from lo9i.core.tools.registry import register


@register("subagents")
@tool
async def delegate(
    task: str,
    runtime: ToolRuntime[Context],
    agent: str = "",
    background: bool = False,
    plugins: list[str] | None = None,
) -> str | ToolMessage:
    """Hand a self-contained task to a subagent, for work whose output you only need a summary of (research
    across many pages, digging through files or logs), and get back its answer. It knows nothing of this
    conversation and can't message, send, schedule or save. `agent`: a named subagent listed under Subagents,
    for a task it's made for; empty for a general one. Calls in one reply run in parallel. How to write
    `task`: the writing-briefs skill.

    `background`: false (the default) waits for the answer, for a quick job you need before replying; it stops
    after a set number of steps. True sends it off to work in the background with no step limit and returns at
    once: for long work, so the user can go on talking meanwhile. Its answer comes back to this conversation when
    it ends, and you're asked to follow it up then. The user follows its progress in the Subagents panel beside this
    conversation in the web app, or /subagents in the terminal app; a chat channel hears only its end.

    `plugins`: plugins listed under Plugin tools whose read-only tools the task needs; it gets those of the
    plugins this conversation loaded anyway. They load for the subagent alone, so don't load_tools them first
    just for it."""
    context = runtime.context
    if context.subagents is None:
        return "Not delegated: subagents aren't available here."
    if unknown := _unreadable(plugins or [], context.subagents):
        return unknown
    given = [*runtime.state.get("loaded_plugins", []), *(plugins or [])]
    try:
        if background and context.background is not None:
            return await _sent_off(task, runtime, context.background, given, agent.strip())
        call_id = runtime.tool_call_id or ""
        answer = await context.subagents.run(task, context, call_id, given, agent.strip())
    except UnknownSubagentError as e:
        return f"Not delegated: {e}"
    return subagent_steps.result(answer, call_id, "delegate")


def _unreadable(named: Collection[str], subagents: Subagents) -> str:
    """Why the plugins named can't go to a subagent, "" when they all can."""
    readable = subagents.readable_plugins()
    if not (missing := sorted(set(named) - readable)):
        return ""
    return (
        f"Not delegated: {', '.join(missing)} has no read-only tools a subagent can use. Plugins it can get: "
        f"{', '.join(sorted(readable)) or 'none'}."
    )


async def _sent_off(
    task: str, runtime: ToolRuntime[Context], starts: BackgroundSubagentStarts, plugins: list[str], agent: str
) -> str:
    context, thread_id = runtime.context, thread_of(runtime.config)
    subagent_id = await starts.start(task, context.user_id, thread_id, context.channel, plugins, agent)
    return (
        f"Sent off as background subagent {subagent_id}. Its answer comes back to this conversation when it ends: "
        "don't wait for it, and don't do its task yourself meanwhile."
    )
