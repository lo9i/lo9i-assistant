import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from assistant.core import inbox, uploads
from assistant.core.agent.conversations import ConversationsMixin
from assistant.core.agent.handoffs import HandoffError, HandoffsMixin
from assistant.core.agent.runs import RunsMixin
from assistant.core.agent.session import Session
from assistant.core.agent.titles import TitlesMixin
from assistant.core.attachments import Attachment, Block, is_reference, to_content
from assistant.core.conversation import briefs, carried, dispatched, ended, handoffs, introduction, moved, pinned, sent
from assistant.core.conversation.handoffs import Handoff
from assistant.core.conversation.turn_header import header_block
from assistant.core.events import Error, Event, Transcribed
from assistant.core.speech import preferences
from assistant.core.speech.transcriber import TranscriptionError
from assistant.core.speech.voice import is_voice, transcribe_voice


class MessagingMixin(HandoffsMixin, RunsMixin, ConversationsMixin, TitlesMixin):
    """Public entry points for sending a message and answering approvals."""

    async def send(
        self, session: Session, text: str, attachments: Sequence[Attachment] = (), brief: str = ""
    ) -> AsyncIterator[Event]:
        """`brief`: for a coding task the assistant wrote for the agent it handed the conversation to
        (daemon/queued.py), the agent's name, kept on the message so the apps don't show it as the user's
        (core/conversation/briefs.py)."""
        voice = [a for a in attachments if is_voice(a)]
        try:
            speech = await preferences.in_use(self._storage.store)
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
            async for event in self._to_agent(session, handoff, text, [t.text for t in transcripts], content, brief):
                yield event
        else:
            notes = await self._notes_for(session)
            message = _message(session, [*notes, *voice_blocks, *content], brief=brief)
            async for event in self._run(session, {"messages": [message]}, text=text, brief=brief):
                yield event
        self._title_in_background(session)

    async def send_dispatched(self, session: Session, dispatch_id: str) -> AsyncIterator[Event]:
        """Sends a message the inbox sent on (core/conversation/dispatch_nodes.py) in `session`'s
        conversation, as it was written: its files and what a voice note said come with it. A message moved
        here from another conversation is left out there (moved.py). A coding task moved out of the inbox
        hands the conversation to its agent first, which then gets it."""
        store = self._storage.store
        kept = await dispatched.load(store, session.user_id, dispatch_id)
        if kept is None or kept.sent_to == session.thread_id:
            yield Error("That message was already sent on here." if kept else "That message is gone.")
            return
        await self._sent_here(session, kept)
        await self._note_activity(session, kept.said)
        handoff = await self._dispatched_handoff(session, kept)
        if isinstance(handoff, Error):
            yield handoff
        brief = kept.handoff["name"] if kept.handoff else ""
        if isinstance(handoff, Handoff):
            events = self._to_agent(session, handoff, kept.said, [], kept.content, brief)
        else:
            notes = await self._header_notes(session)
            message = _message(session, [*notes, *kept.content], kept.carried, brief)
            events = self._run(session, {"messages": [message]}, text=kept.said, brief=brief)
        async for event in events:
            yield event
        self._title_in_background(session)

    async def _dispatched_handoff(self, session: Session, kept: dispatched.Kept) -> Handoff | Error | None:
        """The agent a coding task moved out of the inbox goes to, or why it can't (its folder went away), in
        which case the assistant gets the task."""
        if kept.handoff is None:
            return await handoffs.current(self._storage.store, session.user_id, session.thread_id)
        command, folder = kept.handoff["command"], kept.handoff["folder"]
        try:
            return await self.hand_conversation(session.user_id, session.thread_id, command, folder)
        except HandoffError as e:
            return Error(f"{e} The assistant takes the task instead.")

    async def move_dispatched(self, session: Session, dispatch_id: str | None = None) -> AsyncIterator[Event]:
        """Asks in the inbox where a message it sent on goes instead, the last one when `dispatch_id` is None,
        and sends it on again (a Dispatched event with its id)."""
        store = self._storage.store
        if session.thread_id != await inbox.current(store, session.user_id):
            yield Error("Messages are moved from the inbox.")
            return
        kept = await (
            dispatched.load(store, session.user_id, dispatch_id)
            if dispatch_id
            else dispatched.latest(store, session.user_id)
        )
        if kept is None:
            yield Error("That message is gone." if dispatch_id else "The inbox hasn't sent a message on yet.")
            return
        async for event in self._run(session, {"dispatching": {"move": kept.id}}):
            yield event

    async def _sent_here(self, session: Session, kept: dispatched.Kept) -> None:
        """Where the message was before is told to leave it out, unless that's where it comes back to."""
        store = self._storage.store
        if kept.sent_to:
            await moved.record(store, session.user_id, kept.sent_to, kept.id, kept.said)
        await moved.drop(store, session.user_id, session.thread_id, kept.id)
        await dispatched.sent(store, session.user_id, kept, session.thread_id)

    async def _notes_for(self, session: Session) -> list[Block]:
        """The turn header's notes: the inbox's are those that go with the message wherever it's routed
        (core/conversation/dispatch_nodes.py keeps them with it)."""
        if session.thread_id == await inbox.current(self._storage.store, session.user_id):
            return await self._inbox_notes(session)
        return await self._header_notes(session)

    async def _inbox_notes(self, session: Session) -> list[Block]:
        """Messages sent on this channel from elsewhere, background work started in the inbox that ended,
        and the one-time offer to get to know the user."""
        store = self._storage.store
        sent_here = await sent.take(store, session.user_id, session.channel)
        work_ended = await ended.take(store, session.user_id, session.thread_id, "background_ended_in_inbox")
        offer = await introduction.offer(store, session.user_id, session.channel)
        return [*sent_here, *work_ended, *offer]

    async def _to_agent(
        self,
        session: Session,
        handoff: Handoff,
        text: str,
        transcripts: list[str],
        content: list[Block],
        brief: str = "",
    ) -> AsyncIterator[Event]:
        """The agent gets what was written and said, and where the files sent with it are saved: it runs
        on this computer and reads them from there. The conversation keeps the files as any message does."""
        files = [b for b in content if is_reference(b)]
        said = "\n\n".join(part for part in [text, *transcripts] if part.strip())
        message = _message(session, [*files, {"type": "text", "text": said}], brief=brief)
        to_agent = "\n\n".join(part for part in [said, _files_note(files)] if part)
        async for event in self._handed_off(session, handoff, message, to_agent, text, brief):
            yield event

    async def _header_notes(self, session: Session) -> list[Block]:
        """What goes in the turn header after the date: messages sent here from elsewhere, a change in
        the pinned skills, background work started here that ended, messages moved out of here, and the
        one-time offer to get to know the user."""
        store = self._storage.store
        sent_here = await sent.take(store, session.user_id, session.channel)
        repinned = await pinned.take_notice(store, session.user_id, session.thread_id)
        handed_back = await handoffs.take_notice(store, session.user_id, session.thread_id)
        work_ended = await ended.take(store, session.user_id, session.thread_id)
        moved_away = await moved.take(store, session.user_id, session.thread_id)
        offer = await introduction.offer(store, session.user_id, session.channel)
        return [*sent_here, *repinned, *handed_back, *work_ended, *moved_away, *offer]

    async def resume(self, session: Session, decisions: dict[str, dict[str, Any]]) -> AsyncIterator[Event]:
        """Answer pending approvals. `decisions` maps interrupt id to {"approved": bool, "reason": str}."""
        async for event in self._run(session, Command(resume=decisions)):
            yield event


def _title_text(text: str, transcripts: list[str], attachments: Sequence[Attachment]) -> str:
    """What a new conversation is titled after: the text, else what was said, else the files."""
    return text or " ".join(transcripts) or ", ".join(a.name for a in attachments)


def _message(
    session: Session, content: list[Block], exchange: list[carried.Line] | None = None, brief: str = ""
) -> HumanMessage:
    """`exchange`: the quick exchange in the inbox the message followed up, kept for the apps to show; `brief`: the
    agent a coding task the assistant wrote is for."""
    shown = ({carried.CARRIED: exchange} if exchange else {}) | briefs.kept(brief)
    return HumanMessage(content=[header_block(session.channel, datetime.now(UTC)), *content], additional_kwargs=shown)


def _files_note(files: list[Block]) -> str:
    """The files' full paths, for an agent a conversation is handed to."""
    if not files:
        return ""
    saved = [f["value"]["upload"] for f in files]
    lines = [f"- {uploads.absolute(f['path'])} ({f['name']})" for f in saved]
    return "Files sent with this message, saved on this computer:\n" + "\n".join(lines)
