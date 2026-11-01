"""Live voice calls (core/voice/) from the service's side: the OpenAI key they use, set from Settings → Audio; what a
call is set up with; its requests to the assistant, run as messages of its conversation; and what's said in it,
kept there. The daemon runs the calls themselves (daemon/voice_calls.py)."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from assistant.core import checkpoints, inbox
from assistant.core.agent.messaging import MessagingMixin
from assistant.core.agent.session import Session
from assistant.core.background import short
from assistant.core.conversation import choices, handoffs, prompts, turn_header
from assistant.core.events import Event
from assistant.core.i18n import said
from assistant.core.identity import load_name
from assistant.core.to_the_end import to_the_end
from assistant.core.voice import key as voice_key
from assistant.core.voice import notes, session, spoken
from assistant.core.voice.heard import Line
from assistant.core.voice.key import Source
from assistant.core.voice.realtime import MODEL, RealtimeError

__all__ = ["VoiceCallError", "VoiceCallSettings", "VoiceCallsMixin", "VoiceKeyError"]

# The settings' event: the key lives with the secrets, whose writes clients don't hear about.
_EVENT = "settings"
# The conversation's latest messages the voice is told of, each cut to this many characters.
_RECENT = 8
_RECENT_CHARS = 400


class VoiceKeyError(Exception):
    """OpenAI didn't accept the key."""


class VoiceCallError(Exception):
    """A call can't start: no key, or not in this conversation."""


@dataclass
class VoiceCallSettings:
    """What Settings → Audio shows. Never includes the key."""

    # Where the key calls use comes from: saved for them, the model's (Settings → Model) or .env's; "" when there's
    # none, and calls can't be made.
    key_source: Source
    # The speech-to-speech model calls use.
    model: str


class VoiceCallsMixin(MessagingMixin):
    async def voice_call_settings(self) -> VoiceCallSettings:
        found = await voice_key.current(self._storage.store, self.secrets, self._model)
        return VoiceCallSettings(key_source=found.source, model=MODEL)

    async def set_voice_call_key(self, key: str) -> VoiceCallSettings:
        """Checks the key with OpenAI, then saves it. Raises VoiceKeyError."""
        key = key.strip()
        try:
            await self.realtime.check_key(key)
        except RealtimeError as e:
            raise VoiceKeyError(said("OpenAI didn't accept the key: {error}", error=e)) from e
        await voice_key.save(self._storage.store, self.secrets, key)
        self.bus.publish(_EVENT)
        return await self.voice_call_settings()

    async def remove_voice_call_key(self) -> VoiceCallSettings:
        await voice_key.clear(self._storage.store)
        self.bus.publish(_EVENT)
        return await self.voice_call_settings()

    async def voice_call_key(self) -> str:
        """Raises VoiceCallError when none is set."""
        found = await voice_key.current(self._storage.store, self.secrets, self._model)
        if not found.value:
            raise VoiceCallError(said("Live voice calls need an OpenAI API key: add one in Settings → Audio."))
        return found.value

    async def voice_call_session(self, user_id: str, thread_id: str) -> dict[str, Any]:
        """What a call in the conversation is set up with: the voice's instructions, with the conversation's latest
        messages, and its tool. Raises VoiceCallError in the inbox, which routes what's written there."""
        if thread_id == await inbox.current(self._storage.store, user_id):
            raise VoiceCallError(said("Open a conversation to start a call in it."))
        name = await load_name(self._storage.store)
        recent = _recent(await self._thread_messages(thread_id), name)
        return session.settings(prompts.load("voice_call").format(name=name, recent=recent))

    async def ask_from_voice_call(self, session: Session, request: str, heard: Sequence[Line]) -> AsyncIterator[Event]:
        """The voice model's request, as a message of the call's conversation (channel voice): its turn header says
        it comes from a call, with what was said since the assistant's last answer there. A conversation handed to
        an agent gets it there, as any message."""
        await self._note_activity(session, request)
        handoff = await handoffs.current(self._storage.store, session.user_id, session.thread_id)
        if handoff is not None:
            events = self._to_agent(session, handoff, request, [], [])
        else:
            note = [*await self._header_notes(session), notes.request(heard)]
            text = {"type": "text", "text": request}
            message = HumanMessage([turn_header.header_block(session.channel, datetime.now(UTC)), *note, text])
            events = self._run(session, {"messages": [message]}, text=request)
        async for event in events:
            yield event
        self._title_in_background(session)

    async def keep_said_in_call(self, session: Session, lines: Sequence[Line]) -> bool:
        """Appends what was said to the conversation, once nothing runs there. Returns False, keeping nothing, while
        it waits for the user's answer (an approval): written then, it would end the run that waits."""
        config: RunnableConfig = {"configurable": {"thread_id": session.thread_id}}
        async with self._thread_lock(session.thread_id):
            if (await self._graph.aget_state(config)).next:
                return False
            now = datetime.now(UTC)
            messages = [spoken.message(line, now) for line in lines]
            await to_the_end(self._graph.aupdate_state(config, {"messages": messages}, as_node="agent"))
            await self._index_after_run(session.user_id, session.thread_id)
            await checkpoints.prune(self._storage.checkpointer, session.thread_id)
        await self._note_activity(session, next((line.text for line in lines if line.who == "user"), lines[0].text))
        self.bus.publish("voice_said", thread_id=session.thread_id)
        return True

    async def voice_call_ended(self, session: Session, unheard: Sequence[Line]) -> None:
        """What was said after the call's last request goes to the assistant with the next message there."""
        await notes.keep(self._storage.store, session.user_id, session.thread_id, unheard)
        self._title_in_background(session)


def _recent(messages: Sequence[BaseMessage], name: str) -> str:
    lines = [line for message in messages if (line := _recent_line(message, name))]
    return "\n".join(lines[-_RECENT:])


def _recent_line(message: BaseMessage, name: str) -> str:
    if isinstance(message, HumanMessage):
        text = turn_header.said(message)
        return f"User: {short(text, _RECENT_CHARS)}" if text else ""
    if isinstance(message, AIMessage) and not message.tool_calls:
        text = choices.without_markers(message.text).strip()
        return f"{name}: {short(text, _RECENT_CHARS)}" if text else ""
    return ""
