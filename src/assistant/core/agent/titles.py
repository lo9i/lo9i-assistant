"""Conversation titles written by the worker model: early on, once there is something to go by,
and again from the whole conversation when it's left.

A conversation whose titling fails (the worker model unreachable) waits untitled, and untagged, so
routing can't match it (core/conversation/related.py): it's titled again at its next reply, and the
next title that succeeds anywhere titles the others still waiting, one at a time, stopping at the first
that fails. The daemon's start (title_untitled) puts the conversations that never got one in the wait."""

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
        turns = sum(isinstance(m, HumanMessage) for m in messages)
        if turns in _EARLY_TURNS or (user_id, thread_id) in self._untitled:
            await self._retitle(user_id, thread_id, messages)

    async def _retitle(self, user_id: str, thread_id: str, messages: Sequence[BaseMessage]) -> bool:
        """Keeps the current title when the model fails; a title is never worth failing a turn. The
        conversation then waits to be titled again. Returns whether it was titled."""
        try:
            titled = await self._titler(conversation_text(messages))
        except Exception:
            logger.exception("Couldn't title conversation %s", thread_id)
            self._untitled.add((user_id, thread_id))
            return False
        self._untitled.discard((user_id, thread_id))
        self._title_waiting_in_background()
        async with self._conversations_lock:
            return await conversations.set_title(self._storage.store, user_id, thread_id, titled.title, titled.tags)

    def _title_waiting_in_background(self) -> None:
        """The worker model answered: the conversations waiting for a title get one, unless a pass is on."""
        if not self._untitled or self._titling.locked():
            return
        task = asyncio.create_task(self._title_waiting())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _title_waiting(self) -> int:
        """Titles the conversations waiting for a title, one at a time, until one fails: the model is still
        unreachable, and the next title that succeeds goes on. Returns how many were titled."""
        titled = 0
        async with self._titling:
            while self._untitled:
                waiting = next(iter(self._untitled))
                state = await self._graph.aget_state({"configurable": {"thread_id": waiting[1]}})
                if await self._retitle(*waiting, state.values.get("messages", [])):
                    titled += 1
                elif waiting in self._untitled:
                    break
        return titled
