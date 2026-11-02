"""A fake of OpenAI's Realtime API (core/voice/realtime.py) for live voice calls: no key is real in the tests, so
the calls, their sidebands and their events are the test's."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from assistant.core.voice.realtime import Answer, RealtimeError

GOOD_KEY = "sk-good"


class FakeSideband:
    """The test puts the call's events in; what the daemon sends comes out in `sent`. None ends the call; a
    SidebandLostError drops the connection."""

    def __init__(self) -> None:
        self.incoming: asyncio.Queue[dict[str, Any] | Exception | None] = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []
        self._changed = asyncio.Condition()

    async def send(self, event: dict[str, Any]) -> None:
        async with self._changed:
            self.sent.append(event)
            self._changed.notify_all()

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        while (event := await self.incoming.get()) is not None:
            if isinstance(event, Exception):
                raise event
            yield event

    def say(self, *events: dict[str, Any]) -> None:
        for event in events:
            self.incoming.put_nowait(event)

    async def sent_of(self, kind: str, count: int = 1) -> list[dict[str, Any]]:
        """The events of `kind` the daemon sent, once there are `count`."""
        async with asyncio.timeout(10), self._changed:
            await self._changed.wait_for(lambda: len(self._of(kind)) >= count)
            return self._of(kind)

    def _of(self, kind: str) -> list[dict[str, Any]]:
        return [event for event in self.sent if event["type"] == kind]


class FakeRealtime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.hung_up: list[str] = []
        self.sidebands: list[FakeSideband] = []
        self.opened = asyncio.Condition()
        # Set, the next call is refused with it.
        self.refusal: str = ""

    async def check_key(self, key: str) -> None:
        if key != GOOD_KEY:
            raise RealtimeError("Incorrect API key provided")

    async def call(self, key: str, offer: str, session: dict[str, Any]) -> Answer:
        if self.refusal:
            raise RealtimeError(self.refusal)
        self.calls.append((key, offer, session))
        return Answer(f"rtc_{len(self.calls)}", f"answer to {offer}")

    async def hang_up(self, key: str, call_id: str) -> None:
        self.hung_up.append(call_id)
        for sideband in self.sidebands:
            sideband.incoming.put_nowait(None)

    @asynccontextmanager
    async def sideband(self, key: str, call_id: str) -> AsyncIterator[FakeSideband]:
        sideband = FakeSideband()
        async with self.opened:
            self.sidebands.append(sideband)
            self.opened.notify_all()
        yield sideband

    async def opened_sideband(self, count: int = 1) -> FakeSideband:
        """The sideband opened `count`th, once it is."""
        async with asyncio.timeout(10), self.opened:
            await self.opened.wait_for(lambda: len(self.sidebands) >= count)
            return self.sidebands[count - 1]


def user_said(item_id: str, text: str) -> list[dict[str, Any]]:
    """The events of the user saying `text`: the item added, then its transcription."""
    item = {"id": item_id, "type": "message", "role": "user", "content": [{"type": "input_audio"}]}
    done = {"type": "conversation.item.input_audio_transcription.completed", "item_id": item_id, "transcript": text}
    return [{"type": "conversation.item.added", "item": item}, done]


def voice_said(item_id: str, text: str) -> list[dict[str, Any]]:
    """The events of the voice saying `text`, its response done."""
    item = {"id": item_id, "type": "message", "role": "assistant", "content": [{"type": "output_audio"}]}
    done = {"type": "response.output_audio_transcript.done", "item_id": item_id, "transcript": text}
    spoken = {**item, "content": [{"type": "output_audio", "transcript": text}]}
    return [{"type": "conversation.item.added", "item": item}, done, response_done(spoken)]


def asked(call_id: str, request: str) -> dict[str, Any]:
    """The voice model calling ask_assistant, its response done."""
    arguments = f'{{"request": "{request}"}}'
    return response_done({"type": "function_call", "name": "ask_assistant", "call_id": call_id, "arguments": arguments})


def response_done(*output: dict[str, Any]) -> dict[str, Any]:
    return {"type": "response.done", "response": {"status": "completed", "output": list(output)}}
