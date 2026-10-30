"""The assistant following up on background work that ended (core/background.py) when it failed or its end
asked for it: a run in the conversation it was started in, with no message from the user, whose turn header
says what ended. The daemon sends it once nothing else runs there (daemon/queued.py)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage

from assistant.core.agent.conversations import ConversationsMixin
from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.session import Session
from assistant.core.conversation import ended, handoffs, prompts
from assistant.core.conversation.turn_header import header_block, note_block
from assistant.core.events import Event


class FollowUpsMixin(RunsMixin, ConversationsMixin):
    async def follow_up(self, session: Session, notice: str) -> AsyncIterator[Event]:
        """`notice`: what ended, as the user was told, which the apps show for the run's message. Nothing
        runs in a conversation handed to an agent, or waiting for the user's answer, or once the assistant
        read the end itself: the note then waits for the user's next message there, if it's still owed."""
        store = self._storage.store
        if await handoffs.current(store, session.user_id, session.thread_id):
            return
        if await self.pending_approvals(session.thread_id):
            return
        work_ended = await ended.take(store, session.user_id, session.thread_id)
        if not work_ended:
            return
        await self._note_activity(session, notice)
        message = _message(session, work_ended, notice)
        async for event in self._run(session, {"messages": [message]}, notice=notice):
            yield event


def _message(session: Session, work_ended: list[dict[str, str]], notice: str) -> HumanMessage:
    asked = note_block(prompts.load("background_follow_up"))
    content: list[str | dict] = [header_block(session.channel, datetime.now(UTC)), *work_ended, asked]
    return HumanMessage(content=content, additional_kwargs={ended.FOLLOW_UP: notice})
