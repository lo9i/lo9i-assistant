"""Merging afterwards (core/conversation/skill_homes.py): a message the inbox sent on to a new conversation, whose
single exchange used only a skill that has a home, goes on in that home instead. The exchange's messages are
appended to the home, the chat's messages of it point there, the inbox says "Continued in" the home, and the new
conversation is deleted.

The nightly review (core/proactive/review.py) does the same for the day's conversations that are only about one skill
with a home (`merge_into_homes`): every exchange in them used that skill and nothing else, so no other subject comes
along into the home."""

import logging
from collections import Counter
from datetime import UTC, datetime

from langchain_core.messages import BaseMessage
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
        await self._merge(user_id, listed, home, exchange, [dispatch_id])
        return home.thread_id

    async def merge_into_homes(self, user_id: str, since: datetime) -> dict[str, int]:
        """Merges each conversation written in since `since` whose every exchange used only one skill, the same one,
        into that skill's home, oldest first so the home keeps their order. Left alone: a home, the inbox, an archived
        conversation, one with an exchange that used no skill or another, one still running, waiting for an answer
        or handed to an agent. Returns how many went into each home, by its title."""
        store = self._storage.store
        inbox_id = await inbox.current(store, user_id)
        written = [
            c
            for c in await conversations.recent(store, user_id)
            if _moment(c.updated_at) >= since and not c.archived and not c.home_of and c.thread_id != inbox_id
        ]
        merged: Counter[str] = Counter()
        for conversation in reversed(written):
            if (home := await self._merged_by_topic(user_id, conversation)) is not None:
                merged[home.title] += 1
        return dict(merged)

    async def _merged_by_topic(self, user_id: str, conversation: Conversation) -> Conversation | None:
        """The home it went into; None when it stays."""
        messages = await self._settled_messages(user_id, conversation.thread_id)
        exchanges = skill_homes.exchanges(messages)
        skills = {await self._handled_by(exchange) for exchange in exchanges}
        if len(skills) != 1 or not (skill := skills.pop()):
            return None
        home = await skill_homes.home(self._storage.store, user_id, skill)
        if home is None or home.thread_id == conversation.thread_id:
            return None
        sent_here = [
            i for i, t in (await dispatched.places(self._storage.store, user_id)).items() if t == conversation.thread_id
        ]
        await self._merge(user_id, conversation, home, [m for e in exchanges for m in e], sent_here)
        return home

    async def _merge(
        self,
        user_id: str,
        merged: Conversation,
        home: Conversation,
        messages: list[BaseMessage],
        dispatch_ids: list[str],
    ) -> None:
        await self._append_to_home(user_id, home, messages, merged.channels)
        await self._point_at_home(user_id, merged.thread_id, home, dispatch_ids, merged.channels)
        try:
            await self.delete_conversation(user_id, merged.thread_id)
        except ConversationError:
            logger.warning(
                "Merged %s into %s, but couldn't delete it.", merged.thread_id, home.thread_id, exc_info=True
            )
        logger.info("Merged %s into %s, the home of %s.", merged.thread_id, home.thread_id, home.home_of)

    async def _single_exchange(self, user_id: str, thread_id: str) -> list[BaseMessage]:
        """The conversation's messages when they're one exchange that's over: [] otherwise."""
        exchanges = skill_homes.exchanges(await self._settled_messages(user_id, thread_id))
        return exchanges[0] if len(exchanges) == 1 else []

    async def _settled_messages(self, user_id: str, thread_id: str) -> list[BaseMessage]:
        """The conversation's messages; [] while a run or a question is on it, or it's handed to an agent."""
        if thread_id in self._active_runs or await self.pending_approvals(thread_id):
            return []
        if await handoffs.current(self._storage.store, user_id, thread_id) is not None:
            return []
        state = await self._graph.aget_state(_config(thread_id))
        return state.values.get("messages", [])

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
        self, user_id: str, thread_id: str, home: Conversation, dispatch_ids: list[str], channels: list[str]
    ) -> None:
        """Replying to the chat's messages of the conversation goes on in the home; the messages the inbox sent on to
        it are kept as sent there, and the inbox says so."""
        store = self._storage.store
        await chat_threads.moved(store, user_id, channels, thread_id, home.thread_id)
        for dispatch_id in dispatch_ids:
            if (kept := await dispatched.load(store, user_id, dispatch_id)) is not None:
                await dispatched.sent(store, user_id, kept, home.thread_id)
        inbox_id = await inbox.current(store, user_id)
        if inbox_id is None or not dispatch_ids:
            return
        lines = [continued_line(i, home.thread_id, home.title) for i in dispatch_ids]
        async with self._thread_lock(inbox_id):
            await self._graph.aupdate_state(_config(inbox_id), {"messages": lines}, as_node="agent")


def _config(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}}


def _moment(at: str) -> datetime:
    """A time saved as ISO 8601; one saved without a zone is in UTC."""
    moment = datetime.fromisoformat(at)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
