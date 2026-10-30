"""Moving work out of the inbox (core/inbox.py) without asking: the move_to_conversation tool, for a quick
question in the inbox that turns out to be more, and coding tasks the assistant would start there
(core/agent_tasks/tools.py). The tool writes nothing: the user's message goes on to a new conversation as the inbox
sends one on once a quick exchange goes on too long (core/conversation/dispatch_nodes.py), with the exchange before
it carried, so the new conversation starts on the user's own words. A coding task is the assistant's brief for
its agent, kept the same way. Either way a Dispatched event takes the client to the new conversation once the run
ends, where it's sent as the first message (handed to the coding agent first, for a task)."""

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.config import get_config, get_store, get_stream_writer
from langgraph.prebuilt import ToolRuntime
from langgraph.runtime import get_runtime
from langgraph.store.base import BaseStore
from langgraph.types import Command

from assistant.core import inbox
from assistant.core.context import Context, require_store, thread_of
from assistant.core.conversation import carried, dispatched, ended
from assistant.core.conversation.dispatch_nodes import NEW_TITLE, carried_before, keep_sent_on, new_conversation_line
from assistant.core.conversation.turn_header import said
from assistant.core.events import Dispatched
from assistant.core.tools.registry import register

_MOVED = (
    "Moved the user's message to a new conversation, with the quick exchange before it; the user is taken there "
    "and it's answered there. Say so in one short line; don't start the work here."
)


@register("messages")
@tool
async def move_to_conversation(runtime: ToolRuntime[Context]) -> str | Command:
    """Move the user's message out of the inbox into a new conversation, without asking, as soon as what they ask
    will take more than a couple of turns (a project, a long research, debugging). It goes there as they wrote it,
    with the quick exchange before it, and is answered there."""
    if runtime.context.unattended:
        return "Not moved: nobody is watching this scheduled run."
    store, user_id = require_store(runtime.store), runtime.context.user_id
    if thread_of(runtime.config) != await inbox.current(store, user_id):
        return "Not moved: this is already a conversation of its own."
    messages: list[BaseMessage] = runtime.state["messages"]
    found = _users_last(messages)
    if found is None:
        return "Not moved: there's no message of the user's to move."
    at, message = found
    exchange = carried_before(messages, runtime.state.get("inbox_exchange"), at)
    runtime.stream_writer(await _sent_on(store, user_id, message, exchange))
    # The exchange went with it: the inbox's next message starts afresh.
    answer = ToolMessage(_MOVED, tool_call_id=runtime.tool_call_id, name="move_to_conversation")
    return Command(update={"messages": [answer], "inbox_exchange": None})


def _users_last(messages: list[BaseMessage]) -> tuple[int, HumanMessage] | None:
    """The user's message this run answers, with its place; None when it has nothing they wrote (a follow-up)."""
    at = next((i for i in reversed(range(len(messages))) if isinstance(messages[i], HumanMessage)), None)
    message = messages[at] if at is not None else None
    if at is None or not isinstance(message, HumanMessage) or ended.follow_up_notice(message):
        return None
    return at, message


async def _sent_on(store: BaseStore, user_id: str, message: HumanMessage, exchange: list[carried.Line]) -> Dispatched:
    text = said(message)
    dispatch_id = await keep_sent_on(store, user_id, message, text, exchange)
    line = new_conversation_line(bool(exchange))
    return Dispatched(dispatch_id, "", NEW_TITLE, text, line, carried.shown(exchange))


async def moved_out_of_inbox(title: str, brief: str, handoff: dict[str, str]) -> bool:
    """For a coding task the assistant would start in the inbox while the user watches: moves it to a new
    conversation handed to the agent (`handoff`: its command, folder and name), whose first message is
    `brief`, and says whether it did. Elsewhere it doesn't move and the task starts where it is."""
    context = get_runtime(Context).context
    store = require_store(get_store())
    if context.unattended or thread_of(get_config()) != await inbox.current(store, context.user_id):
        return False
    get_stream_writer()(await _moved(store, context.user_id, title, brief, handoff))
    return True


async def _moved(store: BaseStore, user_id: str, title: str, brief: str, handoff: dict[str, str]) -> Dispatched:
    content = [{"type": "text", "text": brief}]
    dispatch_id = await dispatched.keep(store, user_id, content, brief, handoff)
    line = f"→ Moved “{title}” to a new conversation."
    return Dispatched(dispatch_id, "", title, brief, line, brief=handoff["name"])
