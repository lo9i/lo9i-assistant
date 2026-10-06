import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from assistant.core.agent.conversations import ConversationsMixin
from assistant.core.agent.handoffs import HandoffsMixin
from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.session import Session
from assistant.core.agent.titles import TitlesMixin
from assistant.core.attachments import Attachment, Block, to_content
from assistant.core.conversation import handoffs, introduction, pinned, sent
from assistant.core.conversation.handoffs import Handoff
from assistant.core.conversation.turn_header import header_block
from assistant.core.events import Error, Event, Transcribed
from assistant.core.speech import preferences
from assistant.core.speech.transcriber import TranscriptionError
from assistant.core.speech.voice import is_voice, transcribe_voice


class MessagingMixin(HandoffsMixin, RunsMixin, ConversationsMixin, TitlesMixin):
    """Public entry points for sending a message and answering approvals."""

    async def send(self, session: Session, text: str, attachments: Sequence[Attachment] = ()) -> AsyncIterator[Event]:
        voice = [a for a in attachments if is_voice(a)]
        try:
            speech = await preferences.load(self._storage.store)
            transcripts, voice_blocks = await transcribe_voice(self._transcriber, voice, speech)
            content = await asyncio.to_thread(to_content, text, [a for a in attachments if not is_voice(a)])
        except (TranscriptionError, ValueError) as e:
            yield Error(str(e))
            return
        for transcript in transcripts:
            yield Transcribed(transcript.text, transcript.language)
        await self._note_activity(session, _title_text(text, [t.text for t in transcripts], attachments))
        handoff = await handoffs.current(self._storage.store, session.user_id, session.thread_id)
        if handoff is not None:
            async for event in self._to_agent(session, handoff, text, [t.text for t in transcripts], attachments):
                yield event
        else:
            notes = await self._header_notes(session)
            message = _message(session, [*notes, *voice_blocks, *content])
            async for event in self._run(session, {"messages": [message]}):
                yield event
        self._title_in_background(session)

    async def _to_agent(
        self, session: Session, handoff: Handoff, text: str, transcripts: list[str], attachments: Sequence[Attachment]
    ) -> AsyncIterator[Event]:
        """The agent gets what was written and said; files can't reach it."""
        if any(not is_voice(a) for a in attachments):
            yield Error(f"{handoff.name} takes text only. /{handoff.command} off goes back to send files.")
            return
        said = "\n\n".join(part for part in [text, *transcripts] if part.strip())
        message = _message(session, [{"type": "text", "text": said}])
        async for event in self._handed_off(session, handoff, message, said):
            yield event

    async def _header_notes(self, session: Session) -> list[Block]:
        """What goes in the turn header after the date: messages sent here from elsewhere, a change in
        the pinned skills, and the one-time offer to get to know the user."""
        store = self._storage.store
        sent_here = await sent.take(store, session.user_id, session.channel)
        repinned = await pinned.take_notice(store, session.user_id, session.thread_id)
        handed_back = await handoffs.take_notice(store, session.user_id, session.thread_id)
        offer = await introduction.offer(store, session.user_id, session.channel)
        return [*sent_here, *repinned, *handed_back, *offer]

    async def resume(self, session: Session, decisions: dict[str, dict[str, Any]]) -> AsyncIterator[Event]:
        """Answer pending approvals. `decisions` maps interrupt id to {"approved": bool, "reason": str}."""
        async for event in self._run(session, Command(resume=decisions)):
            yield event


def _title_text(text: str, transcripts: list[str], attachments: Sequence[Attachment]) -> str:
    """What a new conversation is titled after: the text, else what was said, else the files."""
    return text or " ".join(transcripts) or ", ".join(a.name for a in attachments)


def _message(session: Session, content: list[Block]) -> HumanMessage:
    return HumanMessage(content=[header_block(session.channel, datetime.now(UTC)), *content])
