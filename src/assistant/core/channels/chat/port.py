"""The operations a chat in a channel needs, and how they reach the channel's process: each goes down
its stream and waits for the result (core/channels/hub.py)."""

import base64
from dataclasses import dataclass
from typing import Protocol

# (label, button data). The data comes back when the button is pressed.
Buttons = list[tuple[str, str]]


@dataclass(frozen=True)
class ChatLimits:
    """A channel's pace and sizes, which its process gives when it opens its stream."""

    # Seconds between edits of one message: chat services limit how often a bot edits.
    edit_seconds: float = 1.0
    # A reply is shown as drafts while it's at most this long; past it, only its final version.
    draft_limit: int = 3500
    # The longest message; longer replies are split.
    message_limit: int = 3500
    # It can send voice notes, for spoken replies (Settings → Audio).
    voice: bool = False


class ChatPort(Protocol):
    """One chat. Message ids are the channel's own, as text."""

    async def send(self, text: str, *, markdown: bool = False, buttons: Buttons | None = None) -> str: ...
    async def edit(
        self, message: str, text: str, *, markdown: bool = False, buttons: Buttons | None = None
    ) -> None: ...
    async def typing(self) -> None: ...
    async def voice(self, ogg_opus: bytes) -> None: ...


class Operations(Protocol):
    """The hub call that carries out an operation in a channel and returns the message id it gives."""

    async def operate(self, channel: str, kind: str, data: dict[str, object]) -> str: ...


class RemoteChat:
    """A chat in a channel, through its process. `chat` is the channel's id for it; "" is the user's own
    chat there (every paired Telegram account, the owner's Slack DM), for messages the assistant starts.
    Each operation raises DeliveryError when the channel doesn't carry it out."""

    def __init__(self, operations: Operations, channel: str, chat: str) -> None:
        self._operations = operations
        self._channel = channel
        self._chat = chat

    async def send(self, text: str, *, markdown: bool = False, buttons: Buttons | None = None) -> str:
        data = {"text": text, "markdown": markdown, "buttons": _listed(buttons)}
        return await self._operate("send", data)

    async def edit(self, message: str, text: str, *, markdown: bool = False, buttons: Buttons | None = None) -> None:
        data = {"message": message, "text": text, "markdown": markdown, "buttons": _listed(buttons)}
        await self._operate("edit", data)

    async def typing(self) -> None:
        await self._operate("typing", {})

    async def voice(self, ogg_opus: bytes) -> None:
        await self._operate("voice", {"audio": base64.b64encode(ogg_opus).decode()})

    async def _operate(self, kind: str, data: dict[str, object]) -> str:
        return await self._operations.operate(self._channel, kind, {"chat": self._chat, **data})


def _listed(buttons: Buttons | None) -> list[list[str]]:
    return [[label, data] for label, data in buttons or []]
