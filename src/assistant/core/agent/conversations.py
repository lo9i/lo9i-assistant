"""Conversations for clients: list them, show one, and keep the list up to date."""

from dataclasses import replace
from datetime import UTC, datetime

from assistant.core import conversations, home
from assistant.core.agent.session import Session
from assistant.core.agent.titles import TitlesMixin
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.conversation.display import ShownMessage, shown
from assistant.core.conversation.turn_header import channels
from assistant.core.conversations import Conversation

__all__ = ["Conversation", "ConversationsMixin", "ShownMessage"]


class ConversationsMixin(TitlesMixin):
    async def list_conversations(self, user_id: str) -> list[Conversation]:
        """Home first, then newest activity first."""
        home_id = await home.current(self._storage.store, user_id)
        listed = [
            replace(c, home=c.thread_id == home_id) for c in await conversations.recent(self._storage.store, user_id)
        ]
        return sorted(listed, key=lambda c: not c.home)

    async def conversation_messages(self, thread_id: str) -> list[ShownMessage]:
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        return shown(state.values.get("messages", []))

    async def _note_activity(self, session: Session, text: str) -> None:
        """Keeps the list current. Scheduled job runs aren't conversations the user resumes."""
        if session.channel != UNATTENDED_CHANNEL:
            now = datetime.now(UTC).isoformat()
            async with self._conversations_lock:
                await conversations.touch(
                    self._storage.store, session.user_id, session.thread_id, text, session.channel, now
                )

    async def index_conversations(self, user_id: str) -> int:
        """Adds conversations saved before the list existed. Returns how many were added."""
        known = {c.thread_id for c in await conversations.recent(self._storage.store, user_id)}
        added = 0
        for thread_id in await self._saved_threads(user_id):
            if thread_id not in known and await self._index(user_id, thread_id):
                known.add(thread_id)
                added += 1
        return added

    async def title_untitled(self, user_id: str) -> int:
        """Titles conversations that only have their first message as a title (saved before
        titles were written, or the model failed). Returns how many were titled."""
        titled = 0
        for conversation in await conversations.recent(self._storage.store, user_id):
            if not conversation.titled:
                state = await self._graph.aget_state({"configurable": {"thread_id": conversation.thread_id}})
                titled += await self._retitle(user_id, conversation.thread_id, state.values.get("messages", []))
        return titled

    async def fill_channels(self, user_id: str) -> int:
        """Records the channels of conversations listed before channels were recorded, read from
        their messages' turn headers. Returns how many were filled in."""
        filled = 0
        for conversation in await conversations.recent(self._storage.store, user_id):
            if conversation.channels:
                continue
            state = await self._graph.aget_state({"configurable": {"thread_id": conversation.thread_id}})
            found = channels(state.values.get("messages", []))
            if found:
                async with self._conversations_lock:
                    await conversations.set_channels(self._storage.store, user_id, conversation.thread_id, found)
                filled += 1
        return filled

    async def _saved_threads(self, user_id: str) -> list[str]:
        """Collected before any is read: `alist` holds the checkpointer's lock until it finishes,
        so reading a thread while it iterates would wait forever."""
        seen: dict[str, None] = {}
        async for checkpoint in self._storage.checkpointer.alist(None):
            thread_id = checkpoint.config.get("configurable", {}).get("thread_id", "")
            if thread_id.startswith(f"{user_id}:"):
                seen[thread_id] = None
        return list(seen)

    async def _index(self, user_id: str, thread_id: str) -> bool:
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        messages = state.values.get("messages", [])
        first = next((m for m in shown(messages) if m.role == "user"), None)
        if first is None:
            return False
        at = state.created_at or datetime.now(UTC).isoformat()
        conversation = Conversation(
            thread_id, conversations.title_from(first.text), at, at, channels=channels(messages)
        )
        async with self._conversations_lock:
            await conversations.save(self._storage.store, user_id, conversation)
        return True
