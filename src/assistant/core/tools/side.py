"""The suggest_side_conversation tool: the agent suggests moving a focused task out of home
(core/home.py) into a side conversation of its own. The run waits for the answer like for an
approval (core/events.py::SIDE_CONVERSATION); on yes, the client that answered starts the side
conversation once the run ends and sends the brief there as its first message."""

from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import interrupt

from assistant.core import home
from assistant.core.context import Context, require_store, thread_of
from assistant.core.events import SIDE_CONVERSATION
from assistant.core.tools.registry import register


@register("messages")
@tool
async def suggest_side_conversation(title: str, brief: str, runtime: ToolRuntime[Context]) -> str:
    """Suggest moving a focused task out of the home conversation into a side conversation of its
    own, so home stays light. Use it when the user starts work that will take many turns (a
    project, a long research, debugging something) while in home, not for quick asks. `title`: a
    few words. `brief`: everything the side conversation needs to pick the task up, since it starts
    with nothing of this one (the goal, names, paths, decisions made so far). The user decides."""
    if runtime.context.unattended:
        return "Not suggested: nobody is watching this scheduled run."
    if thread_of(runtime.config) != await home.current(require_store(runtime.store), runtime.context.user_id):
        return "Not suggested: this is already a side conversation."
    answer = interrupt(_request(title, brief))
    return _result(title, answer)


def _request(title: str, brief: str) -> dict[str, Any]:
    first_message = f"Carried over from home: {title}\n\n{brief}"
    return {"kind": SIDE_CONVERSATION, "title": title, "brief": brief, "first_message": first_message}


def _result(title: str, answer: Any) -> str:
    if isinstance(answer, dict) and answer.get("moved"):
        return (
            f"The user moved this to a side conversation, {title!r}, which gets the brief as its first "
            "message and goes on from there. Say so in one short line; don't start the task here."
        )
    return "The user wants to keep working on it here."
