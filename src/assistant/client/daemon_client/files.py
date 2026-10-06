from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import FileUnavailableError, UploadedFile


class FilesApi:
    """The files in the user's conversations: the ones they sent and the ones tool results brought."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self) -> list[UploadedFile]:
        """Newest first."""
        return [UploadedFile(**f) for f in await self._transport.request("GET", "/files")]

    async def content(self, file: UploadedFile) -> bytes:
        """The file's bytes, to open or save. Raises FileUnavailableError."""
        errors = {404: FileUnavailableError}
        return await self._transport.content("/files/content", params={"path": file.path}, errors=errors)
