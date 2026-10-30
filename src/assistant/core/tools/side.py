"""Moving work out of the inbox (core/inbox.py) without asking: the move_to_conversation tool, for a quick
question in the inbox that turns out to be more, and coding tasks the assistant would start there
(core/agent_tasks/tools.py). The brief is kept like a message the inbox routes (core/conversation/
dispatched.py), and a Dispatched event takes the client to a new conversation once the run ends, where the
brief is sent as its first message (handed to the coding agent first, for a task)."""

from langchain_core.tools import tool
from langgraph.config import get_config, get_store, get_stream_writer
from langgraph.prebuilt import ToolRuntime
from langgraph.runtime import get_runtime
from langgraph.store.base import BaseStore

from assistant.core import inbox
from assistant.core.context import Context, require_store, thread_of
from assistant.core.conversation import dispatched
from assistant.core.events import Dispatched
from assistant.core.tools.registry import register


@register("messages")
@tool
async def move_to_conversation(title: str, brief: str, runtime: ToolRuntime[Context]) -> str:
    """Move work out of the inbox into a new conversation, without asking, as soon as it will take more than a
    couple of turns (a project, a long research, debugging). `title`: a few words. `brief`: everything the new
    conversation needs, as it has nothing of the inbox (the writing-briefs skill)."""
    if runtime.context.unattended:
        return "Not moved: nobody is watching this scheduled run."
    store, user_id = require_store(runtime.store), runtime.context.user_id
    if thread_of(runtime.config) != await inbox.current(store, user_id):
        return "Not moved: this is already a conversation of its own."
    first_message = f"Carried over from the inbox: {title}\n\n{brief}"
    runtime.stream_writer(await _moved(store, user_id, title, first_message, None))
    return (
        f"Moved this to a new conversation, {title!r}, which gets the brief as its first message and goes on "
        "from there; the user is taken there. Say so in one short line; don't start the work here."
    )


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


async def _moved(
    store: BaseStore, user_id: str, title: str, first_message: str, handoff: dict[str, str] | None
) -> Dispatched:
    content = [{"type": "text", "text": first_message}]
    dispatch_id = await dispatched.keep(store, user_id, content, first_message, handoff)
    line = f"→ Moved “{title}” to a new conversation."
    return Dispatched(dispatch_id, "", title, first_message, line, brief=handoff["name"] if handoff else "")
