from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Notification


class NotificationsApi:
    """The notifications feed: job results and background work that ended, newest first."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self) -> list[Notification]:
        return [Notification(**n) for n in await self._transport.request("GET", "/notifications")]

    async def mark_read(self) -> None:
        await self._transport.request("POST", "/notifications/read")

    async def dismiss(self, notification_id: str) -> None:
        await self._transport.request("DELETE", f"/notifications/{notification_id}")

    async def clear(self) -> None:
        await self._transport.request("DELETE", "/notifications")
