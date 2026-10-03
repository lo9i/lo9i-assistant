from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Alert
from assistant.core.health import Area


class AlertsApi:
    """MCP servers and skills that keep failing, until dismissed or working again."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self) -> list[Alert]:
        return [Alert(**a) for a in await self._transport.request("GET", "/alerts")]

    async def dismiss(self, area: Area, name: str) -> None:
        await self._transport.request("POST", f"/alerts/{area}/{name}/dismiss")
