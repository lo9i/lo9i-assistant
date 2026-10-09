"""Conversation titles written by the worker model: early on, once there is something to go by,
and again from the whole conversation when it's left."""

import asyncio
import logging
from collections.abc import Sequence

from langchain_core.messages import BaseMessage, HumanMessage

from assistant.core import conversations
from assistant.core.agent.base import ServiceBase
from assistant.core.agent.session import Session
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.conversation.titles import conversation_text

logger = logging.getLogger(__name__)

# After these user turns. The first message alone often doesn't say what the conversation becomes.
_EARLY_TURNS = (1, 3)


class TitlesMixin(ServiceBase):
    def _title_in_background(self, session: Session) -> None:
        """After a reply. Scheduled job runs aren't listed, so they get no title."""
        if session.channel == UNATTENDED_CHANNEL:
            return
        task = asyncio.create_task(self._title_early(session.user_id, session.thread_id))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _title_early(self, user_id: str, thread_id: str) -> None:
        state = await self._graph.aget_state({"configurable": {"thread_id": thread_id}})
        messages = state.values.get("messages", [])
        if sum(isinstance(m, HumanMessage) for m in messages) in _EARLY_TURNS:
            await self._retitle(user_id, thread_id, messages)

    async def _retitle(self, user_id: str, thread_id: str, messages: Sequence[BaseMessage]) -> bool:
        """Keeps the current title when the model fails; a title is never worth failing a turn.
        Returns whether it was titled."""
        try:
            titled = await self._titler(conversation_text(messages))
        except Exception:
            logger.exception("Couldn't title conversation %s", thread_id)
            return False
        async with self._conversations_lock:
            return await conversations.set_title(self._storage.store, user_id, thread_id, titled.title, titled.tags)
