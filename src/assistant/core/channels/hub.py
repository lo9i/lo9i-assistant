"""The chat channels' processes as the daemon sees them while they run (docs/channel-plugins.md).

A channel process holds one event stream open (`attach`), giving its chat limits. Every chat operation
(send, edit, typing, voice; core/channels/chat/port.py) goes down the stream and waits for the channel
to confirm it (`operate`), so the sender learns whether it really happened and the id of the message it
sent. An operation for a channel that's away (its process restarting after an update) waits for it to come
back, so a turn in progress goes on showing in its chat once it's back. While the stream is open, the
channel is registered in the outbox and in remote approvals, so `send_message` and scheduled jobs reach it.
The channel also tells what the apps show for it (`set_status`), and gets the buttons pressed there (`act`).
"""

import asyncio
import contextlib
import secrets
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from assistant.core.approvals import RemoteApprovals
from assistant.core.bus import EventBus
from assistant.core.channels.chat.approvals import job_approval_buttons, job_approval_text
from assistant.core.channels.chat.port import OWN_CHAT, ChatLimits, Delivered, RemoteChat
from assistant.core.channels.chat.split import split_text
from assistant.core.i18n import Texts
from assistant.core.outbox import DeliveryError, Outbox

# The channel protocol this daemon speaks (docs/channel-plugins.md). A plugin declares the one its process
# speaks (`protocol:` in its channel section); one that speaks another isn't run (processes.py).
PROTOCOL = 2
# How long an operation waits for the channel to confirm it.
DELIVERY_SECONDS = 30.0
# How long an operation waits for a channel that's away to connect again: its process restarting (a plugin
# update, a crash) takes a few seconds, a first start that builds its environment longer.
RECONNECT_SECONDS = 120.0

SetupKind = Literal["text", "code", "copy", "qr", "action"]
# A channel's commands: {"command": "new", "description": "..."} each.
Commands = list[dict[str, str]]


@dataclass
class SetupItem:
    """A line the apps show for a channel: text, a code to read out, a value to copy, a QR code to scan
    (`value` is what it encodes; each app draws it) or a button (`value` is the action it sends back)."""

    kind: SetupKind
    label: str
    value: str = ""


@dataclass
class ChannelEvent:
    kind: str
    data: dict[str, Any]


def protocol_problem(protocol: int) -> str:
    """Why a channel whose plugin speaks `protocol` can't run here; "" when it can."""
    if protocol < PROTOCOL:
        return "This plugin was written for an older version of lo9i. Update it in Plugins to use it."
    if protocol > PROTOCOL:
        return "This plugin needs a newer version of lo9i. Update lo9i to use it."
    return ""


class ChannelNotConnectedError(Exception):
    """The channel's process isn't connected."""


class _GoneError(Exception):
    """The stream an operation went down ended before the channel confirmed it."""


@dataclass
class _Stream:
    limits: ChatLimits
    events: asyncio.Queue[ChannelEvent] = field(default_factory=asyncio.Queue)
    ended: asyncio.Event = field(default_factory=asyncio.Event)


class ChannelHub:
    name = "channels"

    def __init__(
        self,
        outbox: Outbox,
        approvals: RemoteApprovals,
        bus: EventBus,
        assistant_name: Callable[[], Awaitable[str]],
        commands: Callable[[], Awaitable[Commands]],
        texts: Callable[[], Awaitable[Texts]],
    ) -> None:
        """`commands`: what the channels offer (core/channels/chat/commands.py), in the language chosen, which
        `texts` gives the text of a job's approval in."""
        self._outbox = outbox
        self._approvals = approvals
        self._bus = bus
        self._assistant_name = assistant_name
        self._commands = commands
        self._texts = texts
        self._tokens: dict[str, str] = {}
        self._streams: dict[str, _Stream] = {}
        self._items: dict[str, list[SetupItem]] = {}
        # Operations waiting for their channel to confirm them: id -> (the stream it went down, (error, what it did)).
        self._deliveries: dict[str, tuple[_Stream, asyncio.Future[tuple[str, Delivered]]]] = {}
        # Set when a channel connects, then replaced: what operations waiting for one to come back wait on.
        self._arrived = asyncio.Event()

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

    async def texts(self) -> Texts:
        return await self._texts()

    def connected(self, channel: str) -> bool:
        return channel in self._streams

    def items(self, channel: str) -> list[SetupItem]:
        return self._items.get(channel, [])

    def limits(self, channel: str) -> ChatLimits:
        """What the channel's process gave when it opened its stream; the defaults while it's away."""
        stream = self._streams.get(channel)
        return stream.limits if stream is not None else ChatLimits()

    async def attach(self, channel: str, limits: ChatLimits) -> AsyncGenerator[ChannelEvent]:
        """The channel's events for as long as it reads them. A second stream ends the first."""
        stream = self._open(channel, limits)
        try:
            hello = {"assistant_name": await self._assistant_name(), "commands": await self._commands()}
            yield ChannelEvent("hello", hello)
            while not stream.ended.is_set():
                event = await _next(stream)
                if event is not None:
                    yield event
        finally:
            self._close(channel, stream)

    def set_status(self, channel: str, items: list[SetupItem]) -> None:
        self._items[channel] = items
        self._bus.publish("channels")

    def confirm(self, delivery_id: str, error: str, message: str = "", messages: Sequence[str] = ()) -> bool:
        """The channel's answer to an operation: what went wrong, or the id of the message it sent and every one
        it took (Delivered). False when nothing waits for it any more."""
        _, waiting = self._deliveries.get(delivery_id, (None, None))
        if waiting is None or waiting.done():
            return False
        waiting.set_result((error, Delivered(message, tuple(messages))))
        return True

    def act(self, channel: str, action: str) -> None:
        """Pass a button pressed in an app to the channel. Raises ChannelNotConnectedError."""
        self._push(channel, ChannelEvent("action", {"action": action}))

    async def run(self, stop: asyncio.Event) -> None:
        """Tell the channels when the assistant is renamed (Telegram renames its bot) and when their
        commands change (an agent plugin installed or removed, the language changed)."""
        changes = asyncio.create_task(self._follow_changes())
        try:
            await stop.wait()
        finally:
            changes.cancel()

    async def operate(self, channel: str, kind: str, data: dict[str, Any]) -> Delivered:
        """Have the channel carry out a chat operation and wait until it says it did. Returns what it did: the
        message a `send` sent. While the channel is away, waits up to
        RECONNECT_SECONDS for it to connect again, and sends the operation again then if it went away before
        confirming it: a message it sent just before going may then show twice, which beats a turn that stops
        showing. Raises DeliveryError."""
        deadline = asyncio.get_running_loop().time() + RECONNECT_SECONDS
        while True:
            stream = self._streams.get(channel)
            if stream is not None:
                with contextlib.suppress(_GoneError):
                    return await self._deliver(channel, stream, kind, data)
            if not await self._back(channel, deadline):
                raise DeliveryError(f"{channel} isn't connected.")

    async def _deliver(self, channel: str, stream: _Stream, kind: str, data: dict[str, Any]) -> Delivered:
        """Raises _GoneError when the stream ends before the channel confirms it, DeliveryError otherwise."""
        delivery_id = uuid4().hex
        waiting: asyncio.Future[tuple[str, Delivered]] = asyncio.get_running_loop().create_future()
        self._deliveries[delivery_id] = (stream, waiting)
        try:
            stream.events.put_nowait(ChannelEvent(kind, {"id": delivery_id, **data}))
            error, delivered = await asyncio.wait_for(waiting, DELIVERY_SECONDS)
        except TimeoutError as e:
            raise DeliveryError(f"{channel} didn't confirm the delivery in time.") from e
        finally:
            self._deliveries.pop(delivery_id, None)
        if error:
            raise DeliveryError(error)
        return delivered

    async def _back(self, channel: str, deadline: float) -> bool:
        """Waits until the channel is connected; False when it isn't by the deadline."""
        loop = asyncio.get_running_loop()
        while not self.connected(channel):
            if (left := deadline - loop.time()) <= 0:
                return False
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._arrived.wait(), left)
        return True

    async def _follow_changes(self) -> None:
        name, commands = await self._assistant_name(), await self._commands()
        async for event in self._bus.subscribe(self._bus.last_id):
            if event.kind == "settings" and (new := await self._assistant_name()) != name:
                name = new
                self._broadcast(ChannelEvent("renamed", {"assistant_name": name}))
            # An agent plugin installed or removed, or the language changed.
            if event.kind in ("mcp", "settings") and (offered := await self._commands()) != commands:
                commands = offered
                self._broadcast(ChannelEvent("commands", {"commands": commands}))

    def _open(self, channel: str, limits: ChatLimits) -> _Stream:
        if (previous := self._streams.get(channel)) is not None:
            previous.ended.set()
            self._fail_deliveries(previous)
        stream = self._streams[channel] = _Stream(limits)
        self._outbox.register(channel, _Sender(self, channel))
        self._approvals.register(channel, _Forwarder(self, channel))
        self._arrived.set()
        self._arrived = asyncio.Event()
        self._bus.publish("channels")
        return stream

    def _close(self, channel: str, stream: _Stream) -> None:
        if self._streams.get(channel) is not stream:
            return  # A newer stream replaced it and keeps the registrations.
        del self._streams[channel]
        self._items.pop(channel, None)
        self._outbox.unregister(channel)
        self._approvals.unregister(channel)
        self._fail_deliveries(stream)
        self._bus.publish("channels")

    def _fail_deliveries(self, stream: _Stream) -> None:
        """The operations that went down a stream that ended, unconfirmed: they're sent again once the channel is
        back."""
        for sent_down, waiting in self._deliveries.values():
            if sent_down is stream and not waiting.done():
                waiting.set_exception(_GoneError())

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
    """The outbox's sender for a connected channel (core/outbox.py): the message goes to the user's own
    chat there, split to fit."""

    def __init__(self, hub: ChannelHub, channel: str) -> None:
        self._hub, self._channel = hub, channel

    async def send(self, text: str) -> list[str]:
        """Every message it took: each part's copy in each paired account."""
        chat = RemoteChat(self._hub, self._channel, OWN_CHAT)
        parts = split_text(text, self._hub.limits(self._channel).message_limit)
        return [message for part in parts for message in (await chat.send_copies(part, markdown=True)).every]


class _Forwarder:
    """Remote approvals' forwarder for a connected channel (core/approvals.py): the request goes to the
    user's own chat there, with `ja:`/`jr:` buttons (core/channels/chat/conversations.py answers them)."""

    def __init__(self, hub: ChannelHub, channel: str) -> None:
        self._hub, self._channel = hub, channel

    async def forward(self, interrupt_id: str, title: str, request: dict[str, Any]) -> None:
        chat = RemoteChat(self._hub, self._channel, OWN_CHAT)
        t = await self._hub.texts()
        await chat.send(job_approval_text(t, title, request), buttons=job_approval_buttons(t, interrupt_id))
