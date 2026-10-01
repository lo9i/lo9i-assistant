from uuid import uuid4

from langchain_core.messages import AIMessage

from assistant.core import conversations
from assistant.core.agent.archive import ArchiveMixin
from assistant.core.agent.session import Session


class ConversationError(Exception):
    pass


class ThreadsMixin(ArchiveMixin):
    """Conversations. A client (terminal, web page) holds its own and says when it leaves one; a
    channel without a client (Telegram) keeps its current one here."""

    async def session(self, user_id: str, channel: str) -> Session:
        """The channel's current conversation, started on first use."""
        item = await self._storage.store.aget(_namespace(user_id), channel)
        thread_id = item.value["thread_id"] if item else await self.new_channel_thread(user_id, channel)
        return Session(user_id=user_id, channel=channel, thread_id=thread_id)

    async def new_thread(self, user_id: str) -> str:
        """A new conversation's id. It's saved, and listed, once it has a message."""
        return f"{user_id}:{uuid4().hex[:12]}"

    async def new_channel_thread(self, user_id: str, channel: str) -> str:
        """Start a new conversation for the channel. The one being left is archived in the background."""
        thread_id = await self.new_thread(user_id)
        previous = await self._storage.store.aget(_namespace(user_id), channel)
        await self._storage.store.aput(_namespace(user_id), channel, {"thread_id": thread_id})
        if previous is not None:
            self.leave_thread(user_id, previous.value["thread_id"])
        return thread_id

    async def require_conversation(self, user_id: str, thread_id: str) -> None:
        """Raises ConversationError unless the conversation exists, before a client resumes it."""
        if await conversations.load(self._storage.store, user_id, thread_id) is None:
            raise ConversationError(f"No conversation {thread_id}.")

    def leave_thread(self, user_id: str, thread_id: str) -> None:
        """Nobody is on the conversation any more: archive what's new in it, in the background."""
        self._archive_in_background(thread_id, user_id)

    async def last_reply(self, thread_id: str) -> str:
        """The text of the conversation's last assistant message."""
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        replies = [m for m in state.values.get("messages", []) if isinstance(m, AIMessage)]
        return replies[-1].text.strip() if replies else ""


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("threads", user_id)
