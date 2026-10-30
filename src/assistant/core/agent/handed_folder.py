"""The folder a conversation is handed to, for the web app's side panel (core/handed_folder/): what's inside it, a
file's text and what git says changed, read only while the conversation is with an agent and only inside its folder.
A conversation that isn't shows the user's home folder instead, read the same way, without its changes."""

import asyncio
from pathlib import Path

from assistant.core.agent.base import ServiceBase
from assistant.core.conversation import handoffs
from assistant.core.handed_folder import changes, contents, paths, preview
from assistant.core.handed_folder.changes import FileChange, FolderChanges
from assistant.core.handed_folder.contents import FolderContents, FolderEntry
from assistant.core.handed_folder.paths import HandedFolderError, MissingPathError, OutsideFolderError
from assistant.core.handed_folder.preview import FilePreview

__all__ = [
    "FileChange",
    "FilePreview",
    "FolderChanges",
    "FolderContents",
    "FolderEntry",
    "HandedFolderError",
    "HandedFolderMixin",
    "MissingPathError",
    "NotHandedError",
    "OutsideFolderError",
]


class NotHandedError(HandedFolderError):
    pass


class HandedFolderMixin(ServiceBase):
    async def handed_folder_contents(self, user_id: str, thread_id: str, path: str) -> FolderContents:
        """The files and folders in `path` (relative to the folder, "" for itself). Raises NotHandedError when the
        conversation isn't with an agent, and HandedFolderError's others as contents.contents."""
        return await contents.contents(await self._handed_root(user_id, thread_id), path)

    async def handed_folder_file(self, user_id: str, thread_id: str, path: str) -> FilePreview:
        """A file's text, as preview.preview. Raises as handed_folder_contents."""
        return await preview.preview(await self._handed_root(user_id, thread_id), path)

    async def handed_folder_changes(self, user_id: str, thread_id: str) -> FolderChanges:
        """What git says changed in the folder. Raises NotHandedError, or MissingPathError for a folder gone."""
        return await changes.changes(await self._handed_root(user_id, thread_id))

    async def home_folder_contents(self, path: str) -> FolderContents:
        """The files and folders in `path` of the user's home folder, read as handed_folder_contents reads the
        handed one. Raises HandedFolderError's others as contents.contents."""
        return await contents.contents(await _home_root(), path)

    async def home_folder_file(self, path: str) -> FilePreview:
        """A file of the home folder's text, as preview.preview. Raises as home_folder_contents."""
        return await preview.preview(await _home_root(), path)

    async def _handed_root(self, user_id: str, thread_id: str) -> Path:
        handoff = await handoffs.current(self._storage.store, user_id, thread_id)
        if handoff is None:
            raise NotHandedError("This conversation isn't handed to an agent.")
        return await asyncio.to_thread(paths.root, handoff.folder)


async def _home_root() -> Path:
    return await asyncio.to_thread(lambda: paths.root(str(Path.home())))
