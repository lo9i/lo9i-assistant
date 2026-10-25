from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Alert, AlertArea


class AlertsApi:
    """MCP servers and skills that keep failing, until dismissed or working again, and the health check's new or
    growing causes, until dismissed."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self) -> list[Alert]:
        return [Alert(**a) for a in await self._transport.request("GET", "/alerts")]

    async def dismiss(self, area: AlertArea, name: str) -> None:
        await self._transport.request("POST", f"/alerts/{area}/{name}/dismiss")
