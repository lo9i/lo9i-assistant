"""What a channel's chat does with what the user sends there. A new message goes to the inbox, which
routes it to the conversation it continues or a new one (core/conversation/dispatch_nodes.py); a reply to a
message goes on in that message's conversation; after /new, the next message starts a new conversation;
while the conversation the channel last wrote in is handed to a coding agent, messages go on there; /pin and
/unpin change the skills pinned to it. A button
answers what its message's run waits for. Each run is shown in the chat it came from (turn.py), through the
channel's process, its first reply tagged with a short name of the conversation; every message sent there
is kept with its conversation (threads.py), so replying to it goes on there."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Coroutine, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from assistant.core.agent.handoffs import Agent, AgentFolders, Handoff, HandoffError
from assistant.core.agent.session import Session
from assistant.core.agent.speech import AudioFormat
from assistant.core.attachments import Attachment
from assistant.core.channels.chat.approvals import parse_decision, parse_job_decision
from assistant.core.channels.chat.port import Buttons, ChatLimits, ChatPort, Operations, RemoteChat
from assistant.core.channels.chat.questions import (
    Press,
    answered_text,
    choices,
    parse_press,
    question_buttons,
    question_text,
)
from assistant.core.channels.chat.turn import ChatTurn
from assistant.core.config import settings
from assistant.core.conversation.dispatch_nodes import NEW_TITLE
from assistant.core.conversation.held import CHAT, HeldRun, Origin
from assistant.core.events import ApprovalRequired, Dispatched, Event, is_question
from assistant.core.i18n import Texts, translatable
from assistant.core.outbox import DeliveryError
from assistant.core.skills.store import SkillError
from assistant.core.speech.synthesizer import SynthesisError

logger = logging.getLogger(__name__)

GREETING = translatable(
    "Hi! Send me a message, a voice note, a photo or a document. Each topic gets a conversation of its own: "
    "a new message goes on in the one it's about, or starts one, and replying to one of my messages goes on "
    "in its conversation. /new starts a new conversation with your next message."
)


class Conversations(Protocol):
    """The service calls a channel's chat needs."""

    async def inbox_thread(self, user_id: str) -> str: ...
    async def new_thread(self, user_id: str) -> str: ...
    async def channel_thread(self, user_id: str, channel: str) -> str: ...
    async def channel_wrote(self, user_id: str, channel: str, thread_id: str) -> None: ...
    async def channel_wants_new(self, user_id: str, channel: str) -> None: ...
    async def channel_takes_new(self, user_id: str, channel: str) -> bool: ...
    async def chat_message_thread(self, user_id: str, channel: str, chat: str, message: str) -> str | None: ...
    async def chat_messages_in(
        self, user_id: str, channel: str, chat: str, messages: list[str], thread_id: str
    ) -> None: ...
    async def chat_tag(self, user_id: str, thread_id: str, text: str = "") -> str: ...
    def send(self, session: Session, text: str, attachments: Sequence[Attachment] = ()) -> AsyncIterator[Event]: ...
    def run_held(self, session: Session, run: HeldRun) -> AsyncIterator[Event]: ...
    def send_dispatched(self, session: Session, dispatch_id: str) -> AsyncIterator[Event]: ...
    def resume(self, session: Session, decisions: dict[str, dict[str, Any]]) -> AsyncIterator[Event]: ...
    async def pending_approvals(self, thread_id: str) -> list[ApprovalRequired]: ...
    async def texts(self) -> Texts: ...
    async def conversation_agent(self, user_id: str, thread_id: str) -> Handoff | None: ...
    async def speaks_reply(self, after_voice_message: bool) -> bool: ...
    async def speak(self, text: str, audio_format: AudioFormat = "wav", voice: str = "") -> bytes: ...
    async def agents(self) -> list[Agent]: ...
    async def hand_conversation(self, user_id: str, thread_id: str, command: str, folder: str) -> Handoff: ...
    async def take_back_conversation(self, user_id: str, thread_id: str) -> None: ...
    async def agent_folders(self, user_id: str) -> AgentFolders: ...
    async def pinned_skills(self, user_id: str, thread_id: str) -> list[str]: ...
    async def pin_skill(self, user_id: str, thread_id: str, name: str) -> list[str]: ...
    async def unpin_skill(self, user_id: str, thread_id: str, name: str) -> list[str]: ...


class Runs(Protocol):
    def follow(
        self, channel: str, thread_id: str, events: AsyncIterator[Event], text: str, brief: str = "", held: str = ""
    ) -> AsyncIterator[Event]:
        """Runs `events` where every client sees it (the daemon's runs) and yields them as they come; `brief`:
        the agent `text` is a coding task for, and `held`, the id of a run kept while an update installed, as the
        run is announced."""
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

    async def message(
        self,
        channel: str,
        chat: str,
        text: str,
        attachments: Sequence[Attachment],
        voice: bool,
        reply_to: str = "",
        message: str = "",
    ) -> None:
        """Runs the message and shows it in `chat`, then speaks the reply when Settings → Audio says so.
        `voice`: the user's message was a voice note. `reply_to`: the id of the message it replies to;
        `message`: its own id, kept with the conversation it goes to."""
        where = _Chat(self._channels, channel, chat, await self._conversations.texts(), message, voice)
        thread_id = await self._thread_for(where, reply_to)
        await self._answer(where, thread_id, lambda s: self._conversations.send(s, text, attachments), text)

    async def replay(self, run: HeldRun) -> None:
        """Runs what the user sent in a chat while an update installed (`held.CHAT`), kept until now
        (core/conversation/held.py), and shows it there as it would have been then."""
        data, texts = run.origin.data, await self._conversations.texts()
        where = _Chat(self._channels, run.channel, str(data["chat"]), texts, str(data["message"]), bool(data["voice"]))
        start = lambda s: self._conversations.run_held(s, run)  # noqa: E731
        await self._answer(where, run.thread_id, start, run.text, run.brief, run.id)

    async def _answer(
        self,
        chat: "_Chat",
        thread_id: str,
        start: Callable[[Session], AsyncIterator[Event]],
        text: str,
        brief: str = "",
        held: str = "",
    ) -> None:
        """Shows the run, keeps the user's message with the conversation it went to, and speaks the reply when
        Settings → Audio says so."""
        turn = await self._show(chat, thread_id, start, text, brief=brief, held=held)
        if chat.message:
            owner = settings.owner_id
            await self._conversations.chat_messages_in(owner, chat.channel, chat.id, [chat.message], turn.thread_id)
        await self._speak(chat, turn.final_text, chat.voice)

    async def press(self, channel: str, chat: str, message: str, text: str, data: str) -> None:
        """A button pressed on `message`, whose text is `text`."""
        where = _Chat(self._channels, channel, chat, await self._conversations.texts())
        thread_id = await self._conversations.chat_message_thread(settings.owner_id, channel, chat, message)
        thread_id = thread_id or await self._conversations.channel_thread(settings.owner_id, channel)
        await self._press(where, _Pressed(message, text, data, thread_id))

    def spawn(self, work: Coroutine[Any, Any, None]) -> None:
        """Runs a message or a press in the background: the channel's request answers at once, and what
        follows reaches the chat as operations. What fails is logged."""
        task = asyncio.create_task(_logged(work))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def command(self, channel: str, command: str, text: str = "") -> str:
        """/new, /start, /pin, /unpin or an agent's command with what follows it, and what to answer."""
        t = await self._conversations.texts()
        match command:
            case "new":
                await self._conversations.channel_wants_new(settings.owner_id, channel)
                return t("Your next message starts a new conversation.")
            case "start":
                return t(GREETING)
            case "pin" | "unpin":
                return await self._pin_command(t, channel, command, text.strip())
        agent = next((a for a in await self._conversations.agents() if a.command == command), None)
        if agent is None:
            return t("Unknown command /{command}.", command=command)
        return await self._agent_command(t, channel, agent, text.strip())

    async def _agent_command(self, t: Texts, channel: str, agent: Agent, folder: str) -> str:
        """`/claude <folder>` hands the conversation the channel last wrote in to the agent (a new one when that
        was the inbox), and the channel's messages go on there until `/claude off` takes it back; alone it
        says how, with the folders used before (a chat has no folder picker)."""
        owner = settings.owner_id
        thread_id = await self._conversations.channel_thread(owner, channel)
        if folder == "off":
            await self._conversations.take_back_conversation(owner, thread_id)
            return t("The assistant answers again from your next message.")
        if not folder:
            return await self._how_to_hand(t, agent)
        if thread_id == await self._conversations.inbox_thread(owner):
            thread_id = await self._conversations.new_thread(owner)
        try:
            handoff = await self._conversations.hand_conversation(owner, thread_id, agent.command, folder)
        except HandoffError as e:
            return str(e)
        await self._conversations.channel_wrote(owner, channel, thread_id)
        return t(
            "{agent} answers from your next message, working in {folder}. /{command} off brings the assistant back.",
            agent=handoff.name,
            folder=handoff.folder,
            command=agent.command,
        )

    async def _how_to_hand(self, t: Texts, agent: Agent) -> str:
        offered = await self._conversations.agent_folders(settings.owner_id)
        folders = [offered.workspace, *offered.recent]
        listed = "\n".join(f"/{agent.command} {folder}" for folder in folders)
        return t("Give {agent} a folder to work in, its full path:", agent=agent.name) + f"\n{listed}"

    async def _pin_command(self, t: Texts, channel: str, command: str, skill: str) -> str:
        """`/pin <skill>` and `/unpin <skill>` change the skills pinned to the conversation the channel last wrote
        in, from its next message there (core/conversation/pinned.py); `/pin` alone lists them. Not the inbox's:
        it sends messages on, so a pin there would hold for quick answers only."""
        owner = settings.owner_id
        thread_id = await self._conversations.channel_thread(owner, channel)
        if thread_id == await self._conversations.inbox_thread(owner):
            return t(
                "Skills are pinned to a conversation, and your last message was answered in the inbox. "
                "Reply to one of my messages in the conversation you want, then pin."
            )
        tag = await self._conversations.chat_tag(owner, thread_id)
        if command == "unpin":
            return await self._unpin(t, thread_id, tag, skill)
        return await self._pin(t, thread_id, tag, skill)

    async def _pin(self, t: Texts, thread_id: str, tag: str, skill: str) -> str:
        owner = settings.owner_id
        if not skill:
            pinned = await self._conversations.pinned_skills(owner, thread_id)
            if not pinned:
                return t("No skills pinned in [{tag}]: /pin <skill>.", tag=tag)
            return t("Pinned in [{tag}]: {skills}.", tag=tag, skills=", ".join(pinned))
        try:
            await self._conversations.pin_skill(owner, thread_id, skill)
        except SkillError as e:
            return str(e)
        return t("Pinned {skill} to [{tag}], from your next message there.", skill=skill, tag=tag)

    async def _unpin(self, t: Texts, thread_id: str, tag: str, skill: str) -> str:
        if not skill:
            return t("Which skill? /unpin <skill>.")
        await self._conversations.unpin_skill(settings.owner_id, thread_id, skill)
        return t("Unpinned {skill} from [{tag}], from your next message there.", skill=skill, tag=tag)

    async def _press(self, chat: "_Chat", pressed: "_Pressed") -> None:
        place = chat.channel.capitalize()
        if job := parse_job_decision(pressed.data, place):
            await self._answer_job(chat, pressed, *job)
        elif press := parse_press(pressed.data):
            await self._answer_question(chat, pressed, press)
        elif decision := parse_decision(pressed.data, place):
            await self._answer_approval(chat, pressed, *decision)

    async def _answer_approval(self, chat: "_Chat", pressed: "_Pressed", interrupt_id: str, answer: dict) -> None:
        await chat.port.edit(pressed.message, pressed.text)
        await chat.port.send(chat.t("Approved.") if answer["approved"] else chat.t("Rejected."))
        await self._resume(chat, pressed.thread_id, {interrupt_id: answer})

    async def _answer_question(self, chat: "_Chat", pressed: "_Pressed", press: Press) -> None:
        """A toggle only redraws the buttons; a pick or Done answers and the run goes on."""
        request = await self._waiting(pressed.thread_id, press.interrupt_id, is_question)
        if request is None:
            await chat.port.edit(pressed.message, pressed.text)
            await chat.port.send(chat.t("This question isn't waiting for an answer any more."))
            return
        text = question_text(chat.t, request)
        if not press.answers:
            buttons = question_buttons(chat.t, press.interrupt_id, request, press.picked)
            await chat.port.edit(pressed.message, text, buttons=buttons)
            return
        picked = choices(request, press.picked)
        await chat.port.edit(pressed.message, text)
        await chat.port.send(answered_text(chat.t, picked))
        await self._resume(chat, pressed.thread_id, {press.interrupt_id: {"choices": picked}})

    async def _answer_job(self, chat: "_Chat", pressed: "_Pressed", interrupt_id: str, answer: dict) -> None:
        """A scheduled job's request: the job's run continues on its own, nothing to show here."""
        await chat.port.edit(pressed.message, pressed.text)
        if not self._jobs.answer(interrupt_id, answer):
            await chat.port.send(
                chat.t("This request isn't waiting any more: the job's run already went on without it.")
            )
        elif answer["approved"]:
            await chat.port.send(chat.t("Approved. The job goes on."))
        else:
            await chat.port.send(chat.t("Rejected. The job goes on without it."))

    async def _thread_for(self, chat: "_Chat", reply_to: str) -> str:
        """Where a message goes: the conversation of the message it replies to; a new one after /new; the
        conversation the channel last wrote in while it's handed to a coding agent; else the inbox."""
        owner, conversations = settings.owner_id, self._conversations
        if reply_to and (replied := await conversations.chat_message_thread(owner, chat.channel, chat.id, reply_to)):
            return replied
        if await conversations.channel_takes_new(owner, chat.channel):
            return await conversations.new_thread(owner)
        last = await conversations.channel_thread(owner, chat.channel)
        if await conversations.conversation_agent(owner, last) is not None:
            return last
        return await conversations.inbox_thread(owner)

    async def _resume(self, chat: "_Chat", thread_id: str, decisions: dict[str, dict[str, Any]]) -> None:
        await self._show(chat, thread_id, lambda s: self._conversations.resume(s, decisions), "")

    async def _show(
        self,
        chat: "_Chat",
        thread_id: str,
        start: Callable[[Session], AsyncIterator[Event]],
        text: str,
        named: str = "",
        brief: str = "",
        held: str = "",
    ) -> ChatTurn:
        """Shows the run in `thread_id`; when the inbox sent its message on, the run there instead, whose turn
        is returned. The channel has then last written in the conversation the turn ran in. `named` tags a
        conversation that isn't saved yet; `text` does otherwise. `brief`: the agent `text` is a coding task for,
        written by the assistant (core/conversation/briefs.py); `held`: the id of the run kept while an update
        installed that this one runs."""
        owner = settings.owner_id
        tag = await self._conversations.chat_tag(owner, thread_id, named or text)
        port = _Recording(chat.port, self._conversations, chat, thread_id)
        turn = ChatTurn(port, self._channels.limits(chat.channel), chat.t, thread_id, tag)
        await turn.render(self._run(chat, thread_id, start, text, brief, held))
        if turn.dispatched:
            return await self._go_on(chat, turn.dispatched)
        await self._conversations.channel_wrote(owner, chat.channel, thread_id)
        return turn

    async def _go_on(self, chat: "_Chat", dispatched: Dispatched) -> ChatTurn:
        """To the conversation the inbox sent the message to, or a new one, where it's sent. A new one is
        tagged with the title work moved out of the inbox came with, else with the message's first words."""
        thread_id = dispatched.thread_id or await self._conversations.new_thread(settings.owner_id)
        send = lambda s: self._conversations.send_dispatched(s, dispatched.id)  # noqa: E731
        named = dispatched.title if dispatched.title != NEW_TITLE else dispatched.text
        return await self._show(chat, thread_id, send, dispatched.text, named, dispatched.brief)

    async def _run(
        self,
        chat: "_Chat",
        thread_id: str,
        start: Callable[[Session], AsyncIterator[Event]],
        text: str,
        brief: str = "",
        held: str = "",
    ) -> AsyncIterator[Event]:
        session = Session(settings.owner_id, chat.channel, thread_id, chat.origin())
        async for event in self._runs.follow(chat.channel, thread_id, start(session), text, brief, held):
            yield event

    async def _waiting(
        self, thread_id: str, interrupt_id: str, kind: Callable[[dict[str, Any]], bool]
    ) -> dict[str, Any] | None:
        waiting = await self._conversations.pending_approvals(thread_id)
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
    def __init__(
        self, channels: Channels, channel: str, chat: str, t: Texts, message: str = "", voice: bool = False
    ) -> None:
        self.channel = channel
        self.id = chat
        self.port: ChatPort = RemoteChat(channels, channel, chat)
        # The text shown there, in the language chosen.
        self.t = t
        # What the user sent there that's being answered: its id ("" for a button pressed), and whether it was a
        # voice note.
        self.message = message
        self.voice = voice

    def origin(self) -> Origin:
        """Kept with a run held while an update installs, so `replay` shows it here."""
        return Origin(CHAT, {"chat": self.id, "message": self.message, "voice": self.voice})


class _Recording:
    """The chat, keeping each message sent there with the conversation of the turn that sent it, so replying
    to it goes on there."""

    def __init__(self, port: ChatPort, conversations: Conversations, chat: _Chat, thread_id: str) -> None:
        self._port = port
        self._conversations = conversations
        self._chat = chat
        self._thread_id = thread_id

    async def send(self, text: str, *, markdown: bool = False, buttons: Buttons | None = None) -> str:
        message = await self._port.send(text, markdown=markdown, buttons=buttons)
        if message:
            owner, channel = settings.owner_id, self._chat.channel
            await self._conversations.chat_messages_in(owner, channel, self._chat.id, [message], self._thread_id)
        return message

    async def edit(self, message: str, text: str, *, markdown: bool = False, buttons: Buttons | None = None) -> None:
        await self._port.edit(message, text, markdown=markdown, buttons=buttons)

    async def typing(self) -> None:
        await self._port.typing()

    async def voice(self, ogg_opus: bytes) -> None:
        await self._port.voice(ogg_opus)


@dataclass(frozen=True)
class _Pressed:
    message: str
    # The pressed message's text, to show it again without its buttons.
    text: str
    data: str
    # The conversation of the message pressed on.
    thread_id: str


async def _logged(work: Coroutine[Any, Any, None]) -> None:
    """A channel that goes away mid-turn and doesn't come back in time (core/channels/hub.py, RECONNECT_SECONDS)
    stops showing it; the run goes on, and the apps show it."""
    try:
        await work
    except DeliveryError as e:
        logger.warning("A channel stopped showing a turn: %s", e)
    except Exception:
        logger.exception("A channel's chat failed")
