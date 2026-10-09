"""The suggest_side_conversation tool: the agent suggests moving a focused task out of home
(core/home.py) into a side conversation, a new one or one the user had already started on it (the
turn header names those a message may continue, core/conversation/related.py). The run waits for the
answer like for an approval (core/events.py::SIDE_CONVERSATION); on yes, the client that answered
goes to that conversation once the run ends and sends the brief there."""

from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import interrupt

from assistant.core import conversations, home
from assistant.core.context import Context, require_store, thread_of
from assistant.core.conversations import Conversation
from assistant.core.events import SIDE_CONVERSATION
from assistant.core.tools.registry import register


@register("messages")
@tool
async def suggest_side_conversation(
    title: str, brief: str, runtime: ToolRuntime[Context], continue_in: str = ""
) -> str:
    """Suggest moving a focused task out of the home conversation into a side conversation, so home
    stays light. Use it when the user starts work that will take many turns (a project, a long
    research, debugging something) while in home, not for quick asks; or, even for a quick ask, when
    the message continues a side conversation its turn header names: pass that one's id as
    `continue_in`. `title`: a few words. `brief`: everything the side conversation needs to pick the
    task up (the goal, names, paths, decisions made so far, what the user just asked), since it has
    nothing of this one. The user decides."""
    if runtime.context.unattended:
        return "Not suggested: nobody is watching this scheduled run."
    store, user_id = require_store(runtime.store), runtime.context.user_id
    home_id = await home.current(store, user_id)
    if thread_of(runtime.config) != home_id:
        return "Not suggested: this is already a side conversation."
    target = await conversations.load(store, user_id, continue_in) if continue_in else None
    if continue_in and (target is None or target.thread_id == home_id):
        return f"No side conversation {continue_in}."
    return _result(title, target, interrupt(_request(title, brief, target)))


def _request(title: str, brief: str, target: Conversation | None) -> dict[str, Any]:
    first_message = f"Carried over from home: {title}\n\n{brief}"
    request = {"kind": SIDE_CONVERSATION, "title": title, "brief": brief, "first_message": first_message}
    if target is not None:
        request |= {"title": target.title, "thread_id": target.thread_id}
    return request


def _result(title: str, target: Conversation | None, answer: Any) -> str:
    if not (isinstance(answer, dict) and answer.get("moved")):
        return "The user wants to keep working on it here."
    where = f"back to the side conversation {target.title!r}" if target else f"to a side conversation, {title!r}"
    return (
        f"The user moved this {where}, which gets the brief as its next message and goes on from there. "
        "Say so in one short line; don't start the task here."
    )
