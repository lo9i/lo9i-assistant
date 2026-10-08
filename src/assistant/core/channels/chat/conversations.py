"""What a channel's chat does with what the user sends there: a message runs in the channel's
conversation, a button answers what the run waits for, a command moves between home and a side
conversation. Each run is shown in the chat it came from (turn.py), through the channel's process."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Coroutine, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from assistant.core.agent.session import Session
from assistant.core.agent.speech import AudioFormat
from assistant.core.attachments import Attachment
from assistant.core.channels.chat.approvals import parse_decision, parse_job_decision
from assistant.core.channels.chat.port import ChatLimits, ChatPort, Operations, RemoteChat
from assistant.core.channels.chat.questions import (
    Press,
    answered_text,
    choices,
    parse_press,
    question_buttons,
    question_text,
)
from assistant.core.channels.chat.side import parse_side, side_text
from assistant.core.channels.chat.turn import ChatTurn
from assistant.core.config import settings
from assistant.core.events import ApprovalRequired, Event, is_question, is_side_conversation
from assistant.core.outbox import DeliveryError
from assistant.core.speech.synthesizer import SynthesisError

logger = logging.getLogger(__name__)

GREETING = (
    "Hi! Send me a message, a voice note, a photo or a document. We talk in the home conversation; "
    "/new starts a side conversation and /home goes back."
)
_MOVED = "Moved to a side conversation. /home goes back."


class Conversations(Protocol):
    """The service calls a channel's chat needs."""

    async def session(self, user_id: str, channel: str) -> Session: ...
    def send(self, session: Session, text: str, attachments: Sequence[Attachment] = ()) -> AsyncIterator[Event]: ...
    def resume(self, session: Session, decisions: dict[str, dict[str, Any]]) -> AsyncIterator[Event]: ...
    async def pending_approvals(self, thread_id: str) -> list[ApprovalRequired]: ...
    async def new_channel_thread(self, user_id: str, channel: str) -> str: ...
    async def channel_home(self, user_id: str, channel: str) -> str: ...
    async def speaks_reply(self, after_voice_message: bool) -> bool: ...
    async def speak(self, text: str, audio_format: AudioFormat = "wav", voice: str = "") -> bytes: ...


class Runs(Protocol):
    def follow(self, channel: str, thread_id: str, events: AsyncIterator[Event], text: str) -> AsyncIterator[Event]:
        """Runs `events` where every client sees it (the daemon's runs) and yields them as they come."""
        ...


class JobAnswers(Protocol):
    def answer(self, interrupt_id: str, decision: dict[str, Any]) -> bool: ...


class Channels(Operations, Protocol):
    def limits(self, channel: str) -> ChatLimits: ...


class ChannelChats:
    def __init__(self, conversations: Conversations, runs: Runs, channels: Channels, jobs: JobAnswers) -> None:
        self._conversations = conversations
        self._runs = runs
        self._channels = channels
        self._jobs = jobs
        self._tasks: set[asyncio.Task[None]] = set()

    async def message(self, channel: str, chat: str, text: str, attachments: Sequence[Attachment], voice: bool) -> None:
        """Runs the message and shows it in `chat`, then speaks the reply when Settings → Audio says so.
        `voice`: the user's message was a voice note."""
        where = _Chat(self._channels, channel, chat)
        turn = await self._show(where, lambda s: self._conversations.send(s, text, attachments), text)
        await self._speak(where, turn.final_text, voice)

    async def press(self, channel: str, chat: str, message: str, text: str, data: str) -> None:
        """A button pressed on `message`, whose text is `text`."""
        await self._press(_Chat(self._channels, channel, chat), _Pressed(message, text, data))

    def spawn(self, work: Coroutine[Any, Any, None]) -> None:
        """Runs a message or a press in the background: the channel's request answers at once, and what
        follows reaches the chat as operations. What fails is logged."""
        task = asyncio.create_task(_logged(work))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def command(self, channel: str, command: str) -> str:
        """/new, /home or /start, and what to answer."""
        match command:
            case "new":
                await self._conversations.new_channel_thread(settings.owner_id, channel)
                return "Started a side conversation. /home goes back."
            case "home":
                await self._conversations.channel_home(settings.owner_id, channel)
                return "Back home."
            case "start":
                return GREETING
            case _:
                return f"Unknown command /{command}."

    async def _press(self, chat: "_Chat", pressed: "_Pressed") -> None:
        place = chat.channel.capitalize()
        if job := parse_job_decision(pressed.data, place):
            await self._answer_job(chat, pressed, *job)
        elif side := parse_side(pressed.data):
            await self._answer_side(chat, pressed, *side)
        elif press := parse_press(pressed.data):
            await self._answer_question(chat, pressed, press)
        elif decision := parse_decision(pressed.data, place):
            await self._answer_approval(chat, pressed, *decision)

    async def _answer_approval(self, chat: "_Chat", pressed: "_Pressed", interrupt_id: str, answer: dict) -> None:
        await chat.port.edit(pressed.message, pressed.text)
        await chat.port.send("Approved." if answer["approved"] else "Rejected.")
        await self._resume(chat, {interrupt_id: answer})

    async def _answer_question(self, chat: "_Chat", pressed: "_Pressed", press: Press) -> None:
        """A toggle only redraws the buttons; a pick or Done answers and the run goes on."""
        request = await self._waiting(chat, press.interrupt_id, is_question)
        if request is None:
            await chat.port.edit(pressed.message, pressed.text)
            await chat.port.send("This question isn't waiting for an answer any more.")
            return
        text = question_text(request)
        if not press.answers:
            buttons = question_buttons(press.interrupt_id, request, press.picked)
            await chat.port.edit(pressed.message, text, buttons=buttons)
            return
        picked = choices(request, press.picked)
        await chat.port.edit(pressed.message, text)
        await chat.port.send(answered_text(picked))
        await self._resume(chat, {press.interrupt_id: {"choices": picked}})

    async def _answer_side(self, chat: "_Chat", pressed: "_Pressed", interrupt_id: str, moved: bool) -> None:
        """The run is answered first; on Move, the task then goes on in a side conversation."""
        request = await self._waiting(chat, interrupt_id, is_side_conversation)
        if request is None:
            await chat.port.edit(pressed.message, pressed.text)
            await chat.port.send("This suggestion isn't waiting for an answer any more.")
            return
        await chat.port.edit(pressed.message, side_text(request))
        await self._resume(chat, {interrupt_id: {"moved": moved}})
        if moved:
            await self._move_to_side(chat, str(request.get("first_message", "")))

    async def _answer_job(self, chat: "_Chat", pressed: "_Pressed", interrupt_id: str, answer: dict) -> None:
        """A scheduled job's request: the job's run continues on its own, nothing to show here."""
        await chat.port.edit(pressed.message, pressed.text)
        if not self._jobs.answer(interrupt_id, answer):
            await chat.port.send("This request isn't waiting any more: the job's run already went on without it.")
        elif answer["approved"]:
            await chat.port.send("Approved. The job goes on.")
        else:
            await chat.port.send("Rejected. The job goes on without it.")

    async def _move_to_side(self, chat: "_Chat", first_message: str) -> None:
        await self._conversations.new_channel_thread(settings.owner_id, chat.channel)
        await chat.port.send(_MOVED)
        await self._show(chat, lambda s: self._conversations.send(s, first_message), first_message)

    async def _resume(self, chat: "_Chat", decisions: dict[str, dict[str, Any]]) -> None:
        await self._show(chat, lambda s: self._conversations.resume(s, decisions), "")

    async def _show(self, chat: "_Chat", start: Callable[[Session], AsyncIterator[Event]], text: str) -> ChatTurn:
        turn = ChatTurn(chat.port, self._channels.limits(chat.channel))
        await turn.render(self._run(chat.channel, start, text))
        return turn

    async def _run(
        self, channel: str, start: Callable[[Session], AsyncIterator[Event]], text: str
    ) -> AsyncIterator[Event]:
        session = await self._conversations.session(settings.owner_id, channel)
        async for event in self._runs.follow(channel, session.thread_id, start(session), text):
            yield event

    async def _waiting(
        self, chat: "_Chat", interrupt_id: str, kind: Callable[[dict[str, Any]], bool]
    ) -> dict[str, Any] | None:
        session = await self._conversations.session(settings.owner_id, chat.channel)
        waiting = await self._conversations.pending_approvals(session.thread_id)
        return next((a.request for a in waiting if a.interrupt_id == interrupt_id and kind(a.request)), None)

    async def _speak(self, chat: "_Chat", reply: str, after_voice_message: bool) -> None:
        """Also sends the reply as a voice note when Settings → Audio says so and the channel can."""
        if not reply or not self._channels.limits(chat.channel).voice:
            return
        if not await self._conversations.speaks_reply(after_voice_message):
            return
        try:
            audio = await self._conversations.speak(reply, "ogg")
        except SynthesisError as e:
            await chat.port.send(f"⚠️ {e}")
            return
        await chat.port.voice(audio)


class _Chat:
    def __init__(self, channels: Channels, channel: str, chat: str) -> None:
        self.channel = channel
        self.port: ChatPort = RemoteChat(channels, channel, chat)


@dataclass(frozen=True)
class _Pressed:
    message: str
    # The pressed message's text, to show it again without its buttons.
    text: str
    data: str


async def _logged(work: Coroutine[Any, Any, None]) -> None:
    """A channel that goes away mid-turn stops showing it; the run goes on, and the apps show it."""
    try:
        await work
    except DeliveryError as e:
        logger.warning("A channel stopped showing a turn: %s", e)
    except Exception:
        logger.exception("A channel's chat failed")
