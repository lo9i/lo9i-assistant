from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import UploadedFile


class FilesApi:
    """The files the user sent in their conversations."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self) -> list[UploadedFile]:
        """Newest first."""
        return [UploadedFile(**f) for f in await self._transport.request("GET", "/files")]
