"""Live voice calls (core/voice/), one per conversation at a time: the daemon passes the browser's offer to OpenAI
with the call's settings and its answer back, and keeps a sideband WebSocket on the call. Audio goes between the
browser and OpenAI only.

On the sideband it hears the call's events. What's said is kept in the conversation as it's said, in the call's order
(core/voice/heard.py), a batch at a time, after the run in progress there if any. Each call of the voice model to
ask_assistant runs through the service as a run of the conversation the hub announces like any other, so every app
shows it, and is answered with the assistant's reply, once per call id (core/voice/tool_calls.py). A sideband that
drops while the call goes on is opened again, a few times. When the call ends, what was said after its last request
goes to the assistant with the next message there. A `voice_call` event tells the apps when a call starts and ends."""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from assistant.core.agent import AssistantService, Session, VoiceCallError
from assistant.core.events import ApprovalRequired, Cancelled, Error, Held
from assistant.core.i18n import said
from assistant.core.to_the_end import to_the_end
from assistant.core.voice.heard import Heard, Line
from assistant.core.voice.realtime import Answer, RealtimeError, Sideband, SidebandLostError
from assistant.core.voice.session import ASK
from assistant.core.voice.spoken import VOICE_CHANNEL
from assistant.daemon.runs import Run, RunHub

logger = logging.getLogger(__name__)

# Times a sideband that dropped is opened again in a row, the first after this many seconds, each after twice the last.
_RECONNECTS = 3
_RECONNECT_SECONDS = 1.0
# How long a call that was hung up has to close its sideband before the daemon stops listening.
_HANG_UP_SECONDS = 5


class _Call:
    def __init__(self, service: AssistantService, hub: RunHub, key: str, call_id: str, session: Session) -> None:
        self._service = service
        self._hub = hub
        self._key = key
        self.call_id = call_id
        self.session = session
        self._heard = Heard()
        # What was said since the last request to the assistant, which it hasn't heard.
        self._unheard: list[Line] = []
        # Batches of what was said, kept in the conversation in order; None after the last.
        self._said: asyncio.Queue[list[Line] | None] = asyncio.Queue()
        self._sideband: Sideband | None = None
        self._answering: set[asyncio.Task[None]] = set()
        self._hung_up = False
        self._attending: asyncio.Task[None] | None = None

    def start(self, ended: Callable[[], None]) -> None:
        self._attending = asyncio.create_task(self._attend(), name=f"voice call {self.call_id}")
        self._attending.add_done_callback(lambda _: ended())

    async def hang_up(self) -> None:
        """Returns once the call stopped listening; what was said is kept after that, once no run holds the
        conversation (`ended`)."""
        self._hung_up = True
        try:
            await self._service.realtime.hang_up(self._key, self.call_id)
        except RealtimeError as e:
            logger.warning("Couldn't hang up voice call %s: %s", self.call_id, e)
        if self._attending is None:
            return
        # OpenAI closes the sideband once the call ended, after its last events, which are kept.
        await asyncio.wait({self._attending}, timeout=_HANG_UP_SECONDS)
        self._attending.cancel()

    async def ended(self) -> None:
        if self._attending is not None:
            await asyncio.wait({self._attending})

    async def _attend(self) -> None:
        keeping = asyncio.create_task(self._keep())
        try:
            await self._listen()
        finally:
            await to_the_end(self._finish(keeping))

    async def _listen(self) -> None:
        """Until the call ends, or its sideband can't be opened again."""
        lost = 0
        while True:
            try:
                async with self._service.realtime.sideband(self._key, self.call_id) as sideband:
                    self._sideband = sideband
                    async for event in sideband.events():
                        lost = 0
                        self._on(event)
                return
            except SidebandLostError as e:
                if self._hung_up or lost >= _RECONNECTS:
                    logger.warning("Voice call %s: %s", self.call_id, e)
                    return
                await asyncio.sleep(_RECONNECT_SECONDS * 2**lost)
                lost += 1
            except RealtimeError as e:
                logger.warning("Voice call %s: %s", self.call_id, e)
                return
            finally:
                self._sideband = None

    def _on(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind in _ITEM_ADDED:
            self._heard.added(event.get("item", {}))
        elif kind == "conversation.item.input_audio_transcription.completed":
            self._heard.heard(event.get("item_id", ""), "user", event.get("transcript", ""))
        elif kind == "conversation.item.input_audio_transcription.failed":
            self._heard.heard(event.get("item_id", ""), "user", "")
        elif kind == "response.output_audio_transcript.done":
            self._heard.heard(event.get("item_id", ""), "voice", event.get("transcript", ""))
        elif kind == "response.done":
            self._responded(event.get("response", {}))
        elif kind == "error":
            logger.warning("Voice call %s: OpenAI said %s", self.call_id, event.get("error"))
        self._said_ready(self._heard.ready())

    def _responded(self, response: dict[str, Any]) -> None:
        """A response's spoken words, for those whose transcript didn't come apart (one cut short), and its calls."""
        for item in response.get("output", []):
            if item.get("type") == "message":
                self._heard.heard(item.get("id", ""), "voice", _transcript(item))
            elif item.get("type") == "function_call":
                task = asyncio.create_task(self._answer(item))
                self._answering.add(task)
                task.add_done_callback(self._answering.discard)

    def _said_ready(self, lines: list[Line]) -> None:
        if lines:
            self._unheard += lines
            self._said.put_nowait(lines)

    async def _keep(self) -> None:
        """Keeps what's said in the conversation; while it waits for the user's answer (an approval), it's kept with
        the next batch."""
        waiting: list[Line] = []
        while (lines := await self._said.get()) is not None:
            waiting += lines
            if await self._service.keep_said_in_call(self.session, waiting):
                waiting = []
        if waiting and not await self._service.keep_said_in_call(self.session, waiting):
            logger.warning("Voice call %s ended while its conversation waits for an answer: not kept", self.call_id)

    async def _answer(self, item: dict[str, Any]) -> None:
        call_id = item.get("call_id", "")
        output = await self._service.voice_tool_calls.answer(call_id, lambda: self._ask(item))
        sideband = self._sideband
        if sideband is None:
            return
        try:
            result = {"type": "function_call_output", "call_id": call_id, "output": output}
            await sideband.send({"type": "conversation.item.create", "item": result})
            await sideband.send({"type": "response.create"})
        except RealtimeError as e:
            logger.warning("Voice call %s: couldn't answer %s: %s", self.call_id, call_id, e)

    async def _ask(self, item: dict[str, Any]) -> str:
        """The assistant's reply to the voice model's call, run as a run of the conversation."""
        if item.get("name") != ASK:
            return f"[There's no tool {item.get('name')!r}: ask_assistant is the only one.]"
        request = _request(item.get("arguments", ""))
        if not request:
            return "[The request was empty: say what the user wants.]"
        heard, self._unheard = self._unheard, []
        thread_id = self.session.thread_id
        events = self._service.ask_from_voice_call(self.session, request, heard)
        run = self._hub.start(thread_id, events, VOICE_CHANNEL, text=request)
        return _outcome(await _kinds(self._hub, run)) or await self._service.last_reply(thread_id) or _NO_REPLY

    async def _finish(self, keeping: asyncio.Task[None]) -> None:
        """What's said and not out yet is kept; what the assistant didn't hear goes with the next message there."""
        for task in list(self._answering):
            task.cancel()
        self._said_ready(self._heard.rest())
        self._said.put_nowait(None)
        await asyncio.wait({keeping})
        await self._service.voice_call_ended(self.session, self._unheard)


class VoiceCalls:
    name = "voice calls"

    def __init__(self, service: AssistantService, hub: RunHub) -> None:
        self._service = service
        self._hub = hub
        self._calls: dict[str, _Call] = {}
        # Conversations whose call is being set up: a second one there waits for none of it.
        self._starting: set[str] = set()

    async def start(self, user_id: str, thread_id: str, offer: str) -> Answer:
        """Starts a call in the conversation from the browser's SDP offer and returns OpenAI's answer. Raises
        VoiceCallError (no key, the inbox, a call on there already) or RealtimeError (OpenAI refused)."""
        if thread_id in self._starting or any(c.session.thread_id == thread_id for c in self._calls.values()):
            raise VoiceCallError(said("A call is already on in this conversation."))
        self._starting.add(thread_id)
        try:
            key = await self._service.voice_call_key()
            answer = await self._service.realtime.call(
                key, offer, await self._service.voice_call_session(user_id, thread_id)
            )
        finally:
            self._starting.discard(thread_id)
        call = _Call(self._service, self._hub, key, answer.call_id, Session(user_id, VOICE_CHANNEL, thread_id))
        self._calls[answer.call_id] = call
        call.start(lambda: self._ended(call))
        logger.info("Voice call %s started in %s", answer.call_id, thread_id)
        self._service.bus.publish("voice_call", thread_id=thread_id, call_id=answer.call_id, live=True)
        return answer

    async def end(self, call_id: str) -> bool:
        """Hangs up; False when no such call is on."""
        call = self._calls.get(call_id)
        if call is None:
            return False
        await call.hang_up()
        return True

    async def run(self, stop: asyncio.Event) -> None:
        """Hangs up every call when the daemon stops, and keeps what was said in them."""
        await stop.wait()
        calls = list(self._calls.values())
        await asyncio.gather(*(call.hang_up() for call in calls))
        await asyncio.gather(*(call.ended() for call in calls))

    def _ended(self, call: _Call) -> None:
        self._calls.pop(call.call_id, None)
        logger.info("Voice call %s ended", call.call_id)
        self._service.bus.publish("voice_call", thread_id=call.session.thread_id, call_id=call.call_id, live=False)


_NO_REPLY = "[The assistant gave no answer.]"
# An item added to the call's conversation: `conversation.item.created` is the name earlier versions of the API used.
_ITEM_ADDED = {"conversation.item.added", "conversation.item.created"}


def _request(arguments: str) -> str:
    try:
        parsed = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return arguments.strip()
    return str(parsed.get("request", "")).strip() if isinstance(parsed, dict) else ""


def _transcript(item: dict[str, Any]) -> str:
    return " ".join(str(part.get("transcript") or part.get("text") or "") for part in item.get("content", [])).strip()


async def _kinds(hub: RunHub, run: Run) -> dict[str, dict[str, Any]]:
    """The run's events once it ended, the last of each kind."""
    found: dict[str, dict[str, Any]] = {}
    async for _, event in hub.follow(run, 0):
        if event is not None:
            found[event["type"]] = event
    return found


def _outcome(kinds: dict[str, dict[str, Any]]) -> str:
    """What the voice model is told when the run didn't end with a reply; "" when it did."""
    if (error := kinds.get(Error.__name__)) is not None:
        return f"[The assistant couldn't answer: {error.get('message', '')}]"
    if ApprovalRequired.__name__ in kinds:
        return "[The assistant waits for the user to approve something in the app before it goes on.]"
    if Held.__name__ in kinds:
        return "[lo9i is installing an update: the request runs once it's back.]"
    if Cancelled.__name__ in kinds:
        return "[The user stopped the assistant's answer.]"
    return ""
