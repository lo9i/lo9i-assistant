"""Merging afterwards (core/conversation/skill_homes.py): a message the inbox sent on to a new conversation, whose
single exchange used only a skill that has a home, goes on in that home instead. The exchange's messages are
appended to the home, the chat's messages of it point there, the inbox says "Continued in" the home, and the new
conversation is deleted."""

import logging
from datetime import UTC, datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from lo9i.core import conversations, inbox
from lo9i.core.agent.messaging import MessagingMixin
from lo9i.core.agent.threads import ConversationError, ThreadsMixin
from lo9i.core.channels.chat import threads as chat_threads
from lo9i.core.conversation import dispatched, handoffs, skill_homes
from lo9i.core.conversation.dispatch_nodes import continued_line
from lo9i.core.conversations import Conversation

logger = logging.getLogger(__name__)


class SkillHomesMixin(ThreadsMixin, MessagingMixin):
    async def merge_into_home(self, user_id: str, thread_id: str, dispatch_id: str) -> str | None:
        """Moves the exchange of the message sent on as `dispatch_id` from `thread_id`, a new conversation, into the
        home of the one skill it used, and deletes `thread_id`. Returns the home's id; None when it stays (more than
        one exchange, no skill or no home, a run or a question still on it, handed to an agent)."""
        store = self._storage.store
        skill = await skill_homes.outcome(store, user_id, dispatch_id)
        home = await skill_homes.home(store, user_id, skill) if skill else None
        exchange = await self._single_exchange(user_id, thread_id) if home and home.thread_id != thread_id else []
        listed = await conversations.load(store, user_id, thread_id)
        if home is None or not exchange or listed is None:
            return None
        await self._append_to_home(user_id, home, exchange, listed.channels)
        await self._point_at_home(user_id, thread_id, home, dispatch_id, listed.channels)
        try:
            await self.delete_conversation(user_id, thread_id)
        except ConversationError:
            logger.warning("Merged %s into %s, but couldn't delete it.", thread_id, home.thread_id, exc_info=True)
        logger.info("Merged %s into %s, the home of %s.", thread_id, home.thread_id, skill)
        return home.thread_id

    async def _single_exchange(self, user_id: str, thread_id: str) -> list[BaseMessage]:
        """The conversation's messages when they're one exchange that's over: [] otherwise."""
        if thread_id in self._active_runs or await self.pending_approvals(thread_id):
            return []
        if await handoffs.current(self._storage.store, user_id, thread_id) is not None:
            return []
        state = await self._graph.aget_state(_config(thread_id))
        messages: list[BaseMessage] = state.values.get("messages", [])
        asked = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
        ended = bool(messages) and isinstance(messages[-1], AIMessage) and not messages[-1].tool_calls
        return messages[asked[0] :] if len(asked) == 1 and ended else []

    async def _append_to_home(
        self, user_id: str, home: Conversation, exchange: list[BaseMessage], channels: list[str]
    ) -> None:
        """Appended as a run's messages are, after the home's last reply, and indexed for search and its files."""
        async with self._thread_lock(home.thread_id):
            await self._graph.aupdate_state(_config(home.thread_id), {"messages": exchange}, as_node="agent")
            await self._index_after_run(user_id, home.thread_id)
            await self._index_files_after_run(user_id, home.thread_id)
        now = datetime.now(UTC).isoformat()
        async with self._conversations_lock:
            for channel in channels:
                await conversations.touch(self._storage.store, user_id, home.thread_id, "", channel, now)

    async def _point_at_home(
        self, user_id: str, thread_id: str, home: Conversation, dispatch_id: str, channels: list[str]
    ) -> None:
        """Replying to the chat's messages of the exchange goes on in the home; the message is kept as sent there,
        and the inbox says so."""
        store = self._storage.store
        await chat_threads.moved(store, user_id, channels, thread_id, home.thread_id)
        kept = await dispatched.load(store, user_id, dispatch_id)
        if kept is not None:
            await dispatched.sent(store, user_id, kept, home.thread_id)
        if (inbox_id := await inbox.current(store, user_id)) is not None:
            async with self._thread_lock(inbox_id):
                line = continued_line(dispatch_id, home.thread_id, home.title)
                await self._graph.aupdate_state(_config(inbox_id), {"messages": [line]}, as_node="agent")


def _config(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}
