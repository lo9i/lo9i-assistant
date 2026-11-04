"""Tool outputs of past conversations whole, which search_memory finds only a snippet of (core/conversation/search.py):
read from the conversation's checkpoint as the apps load a tool call (core/conversation/display.py), and only one
the search index holds for that user, so a conversation of someone else's or an output search leaves out (its own
results, a skill's instructions) isn't read."""

from langgraph.checkpoint.base import BaseCheckpointSaver

from lo9i.core.conversation.display import ShownCall, tool_call, tool_call_step
from lo9i.core.conversation.search import MessageIndex


class PastOutputs:
    def __init__(self, checkpointer: BaseCheckpointSaver, index: MessageIndex) -> None:
        self._checkpointer = checkpointer
        self._index = index

    async def read(self, user_id: str, thread_id: str, call_id: str, step: int | None) -> ShownCall | None:
        """The call, or its step at `step` (from 0), with its whole output; None when search has no such output."""
        if not await self._index.has_tool_output(user_id, thread_id, call_id, step):
            return None
        saved = await self._checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
        messages = saved.checkpoint["channel_values"].get("messages", []) if saved else []
        return tool_call(messages, call_id) if step is None else tool_call_step(messages, call_id, step)
