from uuid import uuid4

from langchain_core.messages import AIMessage

from assistant.core.agent.archive import ArchiveMixin
from assistant.core.agent.session import Session


class ThreadsMixin(ArchiveMixin):
    """The user's active conversation, shared by every channel."""

    async def session(self, user_id: str, channel: str) -> Session:
        item = await self._storage.store.aget(_namespace(user_id), "active")
        thread_id = item.value["thread_id"] if item else await self.new_thread(user_id)
        return Session(user_id=user_id, channel=channel, thread_id=thread_id)

    async def new_thread(self, user_id: str) -> str:
        """Start a new conversation. The one being left is archived in the background."""
        previous = await self._storage.store.aget(_namespace(user_id), "active")
        thread_id = f"{user_id}:{uuid4().hex[:12]}"
        await self._storage.store.aput(_namespace(user_id), "active", {"thread_id": thread_id})
        if previous:
            self._archive_in_background(previous.value["thread_id"], user_id)
        return thread_id

    async def last_reply(self, thread_id: str) -> str:
        """The text of the conversation's last assistant message."""
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        replies = [m for m in state.values.get("messages", []) if isinstance(m, AIMessage)]
        return replies[-1].text.strip() if replies else ""


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("threads", user_id)
