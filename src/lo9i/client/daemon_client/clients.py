from lo9i.client.daemon_client.transport import Transport
from lo9i.protocol import ConnectedClient


class ClientsApi:
    """The clients connected to the daemon, this one included."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    @property
    def own_id(self) -> str:
        return self._transport.client_id

    async def list(self) -> list[ConnectedClient]:
        return [ConnectedClient(**c) for c in await self._transport.request("GET", "/clients")]
