from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import InvalidNameError


class IdentityApi:
    """The assistant's name."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def name(self) -> str:
        """Empty when the user hasn't named the assistant."""
        return (await self._transport.request("GET", "/assistant"))["name"]

    async def rename(self, name: str) -> str:
        """Returns the saved name. Raises InvalidNameError."""
        data = await self._transport.request("PUT", "/assistant", json={"name": name}, errors={400: InvalidNameError})
        return data["name"]
