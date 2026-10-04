from typing import Any

from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import ChannelNotConnectedError, ChannelStatus, SetupItem


class ChannelsApi:
    """The chat channels installed as plugins: what each shows for setting it up, and its buttons."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self) -> list[ChannelStatus]:
        return [_status(c) for c in await self._transport.request("GET", "/channels")]

    async def press(self, name: str, action: str) -> None:
        """Raises ChannelNotConnectedError."""
        errors = {409: ChannelNotConnectedError}
        await self._transport.request("POST", f"/channels/{name}/actions/{action}", errors=errors)


def _status(data: dict[str, Any]) -> ChannelStatus:
    return ChannelStatus(**{**data, "items": [SetupItem(**i) for i in data["items"]]})
