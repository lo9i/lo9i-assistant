import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from assistant.core import uploads
from assistant.core.agent.conversations import ConversationsMixin
from assistant.core.agent.handoffs import HandoffsMixin
from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.session import Session
from assistant.core.agent.titles import TitlesMixin
from assistant.core.attachments import Attachment, Block, is_reference, to_content
from assistant.core.conversation import ended, handoffs, introduction, pinned, related, sent
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
            async for event in self._to_agent(session, handoff, text, [t.text for t in transcripts], content):
                yield event
        else:
            notes = await self._header_notes(session, " ".join([text, *(t.text for t in transcripts)]))
            message = _message(session, [*notes, *voice_blocks, *content])
            async for event in self._run(session, {"messages": [message]}):
                yield event
        self._title_in_background(session)

    async def _to_agent(
        self, session: Session, handoff: Handoff, text: str, transcripts: list[str], content: list[Block]
    ) -> AsyncIterator[Event]:
        """The agent gets what was written and said, and where the files sent with it are saved: it runs
        on this computer and reads them from there. The conversation keeps the files as any message does."""
        files = [b for b in content if is_reference(b)]
        said = "\n\n".join(part for part in [text, *transcripts] if part.strip())
        message = _message(session, [*files, {"type": "text", "text": said}])
        to_agent = "\n\n".join(part for part in [said, _files_note(files)] if part)
        async for event in self._handed_off(session, handoff, message, to_agent):
            yield event

    async def _header_notes(self, session: Session, said: str) -> list[Block]:
        """What goes in the turn header after the date: messages sent here from elsewhere, a change in
        the pinned skills, background work started here that ended, side conversations a message in
        home may continue, and the one-time offer to get to know the user."""
        store = self._storage.store
        sent_here = await sent.take(store, session.user_id, session.channel)
        repinned = await pinned.take_notice(store, session.user_id, session.thread_id)
        handed_back = await handoffs.take_notice(store, session.user_id, session.thread_id)
        work_ended = await ended.take(store, session.user_id, session.thread_id)
        related_sides = await related.notes(store, self._storage.search, session.user_id, session.thread_id, said)
        offer = await introduction.offer(store, session.user_id, session.channel)
        return [*sent_here, *repinned, *handed_back, *work_ended, *related_sides, *offer]

    async def resume(self, session: Session, decisions: dict[str, dict[str, Any]]) -> AsyncIterator[Event]:
        """Answer pending approvals. `decisions` maps interrupt id to {"approved": bool, "reason": str}."""
        async for event in self._run(session, Command(resume=decisions)):
            yield event


def _title_text(text: str, transcripts: list[str], attachments: Sequence[Attachment]) -> str:
    """What a new conversation is titled after: the text, else what was said, else the files."""
    return text or " ".join(transcripts) or ", ".join(a.name for a in attachments)


def _message(session: Session, content: list[Block]) -> HumanMessage:
    return HumanMessage(content=[header_block(session.channel, datetime.now(UTC)), *content])


def _files_note(files: list[Block]) -> str:
    """The files' full paths, for an agent a conversation is handed to."""
    if not files:
        return ""
    saved = [f["value"]["upload"] for f in files]
    lines = [f"- {uploads.absolute(f['path'])} ({f['name']})" for f in saved]
    return "Files sent with this message, saved on this computer:\n" + "\n".join(lines)
