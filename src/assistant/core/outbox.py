"""Messages the agent starts itself, for example "message me on Telegram in a minute".

Channel adapters inside the daemon register a sender while they can deliver, and remove it when
they stop. The `send_message` tool calls the sender directly, so it reports real success or failure,
and core never imports an adapter.
"""

from typing import Protocol


class DeliveryError(Exception):
    """The message couldn't be delivered. The text says why."""


class Sender(Protocol):
    async def send(self, text: str) -> None:
        """Deliver `text` to the user. Raises DeliveryError."""
        ...


class Outbox:
    def __init__(self) -> None:
        self._senders: dict[str, Sender] = {}

    def register(self, channel: str, sender: Sender) -> None:
        self._senders[channel] = sender

    def unregister(self, channel: str) -> None:
        self._senders.pop(channel, None)

    @property
    def channels(self) -> list[str]:
        return sorted(self._senders)

    async def send(self, channel: str, text: str) -> None:
        """Raises DeliveryError when nothing can deliver on `channel` right now, or delivery fails."""
        sender = self._senders.get(channel)
        if sender is None:
            available = ", ".join(self.channels) or "none"
            raise DeliveryError(f"Can't send on {channel} right now (available: {available}).")
        await sender.send(text)
