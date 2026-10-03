from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import MemorySnapshot


class MemoryApi:
    """What the assistant remembers about the user."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def snapshot(self) -> MemorySnapshot:
        return MemorySnapshot(**await self._transport.request("GET", "/memory"))

    async def set_profile_section(self, section: str, items: list[str]) -> MemorySnapshot:
        body = {"items": items}
        return MemorySnapshot(**await self._transport.request("PUT", f"/memory/profile/{section}", json=body))
