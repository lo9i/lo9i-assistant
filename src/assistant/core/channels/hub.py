"""The chat channels' processes as the daemon sees them while they run (docs/channel-plugins.md).

A channel process holds one event stream open (`attach`). While it's open, the channel is
registered in the outbox and in remote approvals, so `send_message` and scheduled jobs reach it:
each delivery goes down the stream and waits for the channel to confirm it, so the sender learns
whether it really arrived. The channel also tells what the apps show for it (`set_status`), and
gets the buttons pressed there (`act`).
"""

import asyncio
import secrets
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from assistant.core.approvals import RemoteApprovals
from assistant.core.bus import EventBus
from assistant.core.outbox import DeliveryError, Outbox

# How long a delivery waits for the channel to confirm it.
DELIVERY_SECONDS = 30.0

SetupKind = Literal["text", "code", "copy", "action"]


@dataclass
class SetupItem:
    """A line the apps show for a channel: text, a code to read out, a value to copy, or a button
    (`value` is the action it sends back)."""

    kind: SetupKind
    label: str
    value: str = ""


@dataclass
class ChannelEvent:
    kind: str
    data: dict[str, Any]


class ChannelNotConnectedError(Exception):
    """The channel's process isn't connected."""


@dataclass
class _Stream:
    events: asyncio.Queue[ChannelEvent] = field(default_factory=asyncio.Queue)
    ended: asyncio.Event = field(default_factory=asyncio.Event)


class ChannelHub:
    name = "channels"

    def __init__(
        self, outbox: Outbox, approvals: RemoteApprovals, bus: EventBus, assistant_name: Callable[[], Awaitable[str]]
    ) -> None:
        self._outbox = outbox
        self._approvals = approvals
        self._bus = bus
        self._assistant_name = assistant_name
        self._tokens: dict[str, str] = {}
        self._streams: dict[str, _Stream] = {}
        self._items: dict[str, list[SetupItem]] = {}
        # Deliveries waiting for their channel to confirm them: id -> (channel, the channel's error).
        self._deliveries: dict[str, tuple[str, asyncio.Future[str]]] = {}

    def issue_token(self, channel: str) -> str:
        """A new token for the channel's process, replacing the one it had."""
        self.revoke(channel)
        token = secrets.token_urlsafe(32)
        self._tokens[token] = channel
        return token

    def revoke(self, channel: str) -> None:
        for token in [t for t, name in self._tokens.items() if name == channel]:
            del self._tokens[token]

    def channel_for(self, token: str) -> str | None:
        return self._tokens.get(token)

    def connected(self, channel: str) -> bool:
        return channel in self._streams

    def items(self, channel: str) -> list[SetupItem]:
        return self._items.get(channel, [])

    async def attach(self, channel: str) -> AsyncGenerator[ChannelEvent]:
        """The channel's events for as long as it reads them. A second stream ends the first."""
        stream = self._open(channel)
        try:
            yield ChannelEvent("hello", {"assistant_name": await self._assistant_name()})
            while not stream.ended.is_set():
                event = await _next(stream)
                if event is not None:
                    yield event
        finally:
            self._close(channel, stream)

    def set_status(self, channel: str, items: list[SetupItem]) -> None:
        self._items[channel] = items
        self._bus.publish("channels")

    def confirm(self, delivery_id: str, error: str) -> bool:
        """The channel's answer to a delivery. False when nothing waits for it any more."""
        _, waiting = self._deliveries.get(delivery_id, ("", None))
        if waiting is None or waiting.done():
            return False
        waiting.set_result(error)
        return True

    def act(self, channel: str, action: str) -> None:
        """Pass a button pressed in an app to the channel. Raises ChannelNotConnectedError."""
        self._push(channel, ChannelEvent("action", {"action": action}))

    async def run(self, stop: asyncio.Event) -> None:
        """Tell the channels when the assistant is renamed (Telegram renames its bot)."""
        renames = asyncio.create_task(self._follow_renames())
        try:
            await stop.wait()
        finally:
            renames.cancel()

    async def deliver(self, channel: str, kind: str, data: dict[str, Any]) -> None:
        """Send the channel something to deliver and wait until it says it did. Raises DeliveryError."""
        delivery_id = uuid4().hex
        waiting: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._deliveries[delivery_id] = (channel, waiting)
        try:
            self._push(channel, ChannelEvent(kind, {"id": delivery_id, **data}))
            error = await asyncio.wait_for(waiting, DELIVERY_SECONDS)
        except ChannelNotConnectedError as e:
            raise DeliveryError(f"{channel} isn't connected.") from e
        except TimeoutError as e:
            raise DeliveryError(f"{channel} didn't confirm the delivery in time.") from e
        finally:
            self._deliveries.pop(delivery_id, None)
        if error:
            raise DeliveryError(error)

    async def _follow_renames(self) -> None:
        name = await self._assistant_name()
        async for event in self._bus.subscribe(self._bus.last_id):
            if event.kind == "settings" and (new := await self._assistant_name()) != name:
                name = new
                self._broadcast(ChannelEvent("renamed", {"assistant_name": name}))

    def _open(self, channel: str) -> _Stream:
        if (previous := self._streams.get(channel)) is not None:
            previous.ended.set()
        stream = self._streams[channel] = _Stream()
        self._outbox.register(channel, _Sender(self, channel))
        self._approvals.register(channel, _Forwarder(self, channel))
        self._bus.publish("channels")
        return stream

    def _close(self, channel: str, stream: _Stream) -> None:
        if self._streams.get(channel) is not stream:
            return  # A newer stream replaced it and keeps the registrations.
        del self._streams[channel]
        self._items.pop(channel, None)
        self._outbox.unregister(channel)
        self._approvals.unregister(channel)
        for name, waiting in self._deliveries.values():
            if name == channel and not waiting.done():
                waiting.set_result(f"{channel} disconnected before confirming the delivery.")
        self._bus.publish("channels")

    def _push(self, channel: str, event: ChannelEvent) -> None:
        stream = self._streams.get(channel)
        if stream is None:
            raise ChannelNotConnectedError(f"{channel} isn't connected.")
        stream.events.put_nowait(event)

    def _broadcast(self, event: ChannelEvent) -> None:
        for stream in self._streams.values():
            stream.events.put_nowait(event)


async def _next(stream: _Stream) -> ChannelEvent | None:
    """The stream's next event, or None once it's ended."""
    getting = asyncio.ensure_future(stream.events.get())
    ending = asyncio.ensure_future(stream.ended.wait())
    try:
        await asyncio.wait({getting, ending}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        ending.cancel()
        if not getting.done():
            getting.cancel()
    return getting.result() if getting.done() else None


class _Sender:
    """The outbox's sender for a connected channel (core/outbox.py)."""

    def __init__(self, hub: ChannelHub, channel: str) -> None:
        self._hub, self._channel = hub, channel

    async def send(self, text: str) -> None:
        await self._hub.deliver(self._channel, "deliver", {"text": text})


class _Forwarder:
    """Remote approvals' forwarder for a connected channel (core/approvals.py)."""

    def __init__(self, hub: ChannelHub, channel: str) -> None:
        self._hub, self._channel = hub, channel

    async def forward(self, interrupt_id: str, title: str, request: dict[str, Any]) -> None:
        data = {"interrupt_id": interrupt_id, "title": title, "request": request}
        await self._hub.deliver(self._channel, "approval", data)
