"""Conversations for clients: list them, show one, and keep the list up to date."""

from dataclasses import replace
from datetime import UTC, datetime

from assistant.core import conversations, inbox
from assistant.core.agent.session import Session
from assistant.core.agent.threads import ConversationError
from assistant.core.agent.titles import TitlesMixin
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.conversation.display import ShownCall, ShownMessage, shown, tool_call
from assistant.core.conversation.turn_header import channels
from assistant.core.conversations import Conversation

__all__ = ["Conversation", "ConversationsMixin", "ShownCall", "ShownMessage"]


class ConversationsMixin(TitlesMixin):
    async def list_conversations(self, user_id: str) -> list[Conversation]:
        """Newest activity first, the inbox marked."""
        inbox_id = await inbox.current(self._storage.store, user_id)
        return [
            replace(c, inbox=c.thread_id == inbox_id) for c in await conversations.recent(self._storage.store, user_id)
        ]

    async def conversation_messages(self, thread_id: str) -> list[ShownMessage]:
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        return shown(state.values.get("messages", []))

    async def messages_before_run(self, thread_id: str) -> list[ShownMessage]:
        """Its messages up to its run in progress, all of them when none runs, for a client that replays that
        run's events from its start (daemon/runs.py). A run that starts while they're read stops them too, and
        what came before a run never changes, so the run's own messages are never shown twice."""
        before = self._run_starts.get(thread_id)
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        start = before if before is not None else self._run_starts.get(thread_id)
        return shown(state.values.get("messages", [])[:start])

    async def conversation_tool_call(self, thread_id: str, call_id: str) -> ShownCall:
        """A tool call in full, which its conversation's messages show only the start of (`partial`). Raises
        ConversationError when the conversation has no such call."""
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        call = tool_call(state.values.get("messages", []), call_id)
        if call is None:
            raise ConversationError("No such tool call in this conversation.")
        return call

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
        """Titles conversations that only have their first message as a title, or no tags (saved
        before titles or tags were written, or the model failed while the daemon was down). An archived
        one keeps its title. They wait to be titled like any whose titling failed, so when the model
        can't be reached the pass stops at the first, and the next title that succeeds goes on (titles.py).
        Returns how many were titled."""
        for conversation in await conversations.recent(self._storage.store, user_id):
            if not (conversation.titled and conversation.tags) and not conversation.archived:
                self._untitled.add((user_id, conversation.thread_id))
        return await self._title_waiting()

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
