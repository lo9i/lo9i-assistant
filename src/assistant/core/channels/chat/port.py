"""The operations a chat in a channel needs, and how they reach the channel's process: each goes down
its stream and waits for the result (core/channels/hub.py)."""

import base64
from dataclasses import dataclass
from typing import Protocol

# (label, button data). The data comes back when the button is pressed.
Buttons = list[tuple[str, str]]

# The chat id of the user's own chat on a channel, for what the assistant starts: every paired Telegram
# account, the owner's Slack DM.
OWN_CHAT = ""


@dataclass(frozen=True)
class Delivered:
    """What a channel says it did for an operation: the id of the message a `send` sent (the one to edit), and
    every message it took: in the user's own chat, a copy in each paired Telegram account."""

    message: str = ""
    messages: tuple[str, ...] = ()

    @property
    def every(self) -> list[str]:
        """Every message it took; just `message` from a channel that doesn't list them."""
        return list(self.messages) or ([self.message] if self.message else [])


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
        self,
        message: str,
        text: str,
        *,
        markdown: bool = False,
        buttons: Buttons | None = None,
        keep_text: bool = False,
    ) -> None: ...
    async def typing(self) -> None: ...
    async def voice(self, ogg_opus: bytes) -> None: ...


class Operations(Protocol):
    """The hub call that carries out an operation in a channel and returns what it says it did."""

    async def operate(self, channel: str, kind: str, data: dict[str, object]) -> Delivered: ...


class RemoteChat:
    """A chat in a channel, through its process. `chat` is the channel's id for it; "" is the user's own
    chat there (every paired Telegram account, the owner's Slack DM), for messages the assistant starts.
    `reply_to`: the message what it sends answers (the user's, or the one whose button was pressed), which Slack
    posts in that message's thread and Telegram quotes, so the chat reads as threads.
    Each operation raises DeliveryError when the channel doesn't carry it out."""

    def __init__(self, operations: Operations, channel: str, chat: str, reply_to: str = "") -> None:
        self._operations = operations
        self._channel = channel
        self._chat = chat
        self._reply_to = reply_to

    async def send(self, text: str, *, markdown: bool = False, buttons: Buttons | None = None) -> str:
        return (await self.send_copies(text, markdown=markdown, buttons=buttons)).message

    async def send_copies(self, text: str, *, markdown: bool = False, buttons: Buttons | None = None) -> Delivered:
        """Sends it, and says every message it took (in the user's own chat, one per paired account)."""
        data: dict[str, object] = {"text": text, "markdown": markdown, "buttons": _listed(buttons)}
        if self._reply_to:
            data["reply_to"] = self._reply_to
        return await self._operate("send", data)

    async def edit(
        self,
        message: str,
        text: str,
        *,
        markdown: bool = False,
        buttons: Buttons | None = None,
        keep_text: bool = False,
    ) -> None:
        """`keep_text`: `text` is the message's own, as a press gave it, and only its buttons change; a channel that can
        change only those keeps its formatting, which the text a press gives may have lost (Telegram's)."""
        data: dict[str, object] = {"message": message, "text": text, "markdown": markdown, "buttons": _listed(buttons)}
        if keep_text:
            data["keep_text"] = True
        await self._operate("edit", data)

    async def typing(self) -> None:
        await self._operate("typing", {})

    async def voice(self, ogg_opus: bytes) -> None:
        await self._operate("voice", {"audio": base64.b64encode(ogg_opus).decode()})

    async def _operate(self, kind: str, data: dict[str, object]) -> Delivered:
        return await self._operations.operate(self._channel, kind, {"chat": self._chat, **data})


def _listed(buttons: Buttons | None) -> list[list[str]]:
    return [[label, data] for label, data in buttons or []]
