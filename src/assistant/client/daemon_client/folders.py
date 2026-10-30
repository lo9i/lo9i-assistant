from urllib.parse import quote

from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import (
    DeletingOffError,
    FileChange,
    FileDiff,
    FilePreview,
    FolderChanges,
    FolderContents,
    FolderEntry,
    HandedFolderError,
    MissingPathError,
)

_ERRORS = {400: HandedFolderError, 403: DeletingOffError, 404: MissingPathError}


class ShownFolder:
    """A folder as the folder panel shows it: the one a conversation is handed to, or the home folder beside one that
    isn't, which has no changes (`has_changes`). Paths are relative to it, "" for itself. Every call raises
    HandedFolderError for a path outside it or one it doesn't show, MissingPathError for one that isn't there or a
    conversation no longer handed to an agent."""

    def __init__(self, transport: Transport, base: str, has_changes: bool) -> None:
        self._transport = transport
        self._base = base
        self.has_changes = has_changes

    async def contents(self, path: str = "") -> FolderContents:
        """Folders first, then files, by name; in the handed folder, those git says were deleted too."""
        found = await self._get("", path)
        entries = [FolderEntry(**entry) for entry in found["entries"]]
        return FolderContents(found["path"], entries, found["truncated"])

    async def file(self, path: str) -> FilePreview:
        """Its text to preview, its start for a big one; none for a file that isn't text."""
        return FilePreview(**await self._get("/file", path))

    async def changes(self) -> FolderChanges | None:
        """What git says changed; None for the home folder, whose changes aren't shown."""
        if not self.has_changes:
            return None
        found = await self._transport.request("GET", f"{self._base}/changes", errors=_ERRORS)
        listed = [FileChange(**change) for change in found["changes"]]
        return FolderChanges(found["repository"], listed, found["truncated"])

    async def diff(self, path: str) -> FileDiff:
        """What changed in a file git lists as changed."""
        return FileDiff(**await self._get("/diff", path))

    async def delete(self, path: str) -> None:
        """Moves a file to the system's trash. Raises DeletingOffError while deleting is turned off."""
        await self._transport.request("DELETE", f"{self._base}/file", params={"path": path}, errors=_ERRORS)

    async def _get(self, route: str, path: str) -> dict:
        return await self._transport.request("GET", f"{self._base}{route}", params={"path": path}, errors=_ERRORS)


class FoldersApi:
    """The folder panel's folders, and whether it may delete their files (Settings → General, off at first)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def handed(self, thread_id: str) -> ShownFolder:
        """The folder the conversation is handed to."""
        return ShownFolder(self._transport, f"/conversations/{quote(thread_id, safe='')}/agent/folder", True)

    def home(self) -> ShownFolder:
        """The user's home folder, shown beside a conversation not handed to an agent."""
        return ShownFolder(self._transport, "/folders/home", False)

    async def deleting(self) -> bool:
        return (await self._transport.request("GET", "/settings/folder-deleting"))["enabled"]

    async def set_deleting(self, enabled: bool) -> bool:
        found = await self._transport.request("PUT", "/settings/folder-deleting", json={"enabled": enabled})
        return found["enabled"]
