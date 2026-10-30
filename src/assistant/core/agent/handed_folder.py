"""The folder a conversation is handed to, for the apps' folder panel (core/handed_folder/): what's inside it, what
git says was deleted there among it, a file's text, what git says changed and a changed file's diff, read only while
the conversation is with an agent and only inside its folder. A conversation that isn't shows the user's home folder
instead, read the same way, without its changes. The one change the panel makes is deleting a file the user picked in
either, to the system's trash, and only once the user turned that on in Settings (deleting_setting.py)."""

import asyncio
from pathlib import Path

from assistant.core.agent.base import ServiceBase
from assistant.core.conversation import handoffs
from assistant.core.handed_folder import changes, contents, deleting, deleting_setting, diff, paths, preview, tree
from assistant.core.handed_folder.changes import FileChange, FolderChanges
from assistant.core.handed_folder.contents import FolderContents, FolderEntry
from assistant.core.handed_folder.diff import FileDiff
from assistant.core.handed_folder.paths import HandedFolderError, MissingPathError, OutsideFolderError
from assistant.core.handed_folder.preview import FilePreview
from assistant.core.handed_folder.tree import FolderRefresh, ListedFolder

__all__ = [
    "DeletingOffError",
    "FileChange",
    "FileDiff",
    "FilePreview",
    "FolderChanges",
    "FolderContents",
    "FolderEntry",
    "FolderRefresh",
    "HandedFolderError",
    "HandedFolderMixin",
    "ListedFolder",
    "MissingPathError",
    "NotHandedError",
    "OutsideFolderError",
]


class NotHandedError(HandedFolderError):
    pass


class DeletingOffError(HandedFolderError):
    """Deleting files from the panel is turned off in Settings."""


class HandedFolderMixin(ServiceBase):
    async def handed_folder_contents(self, user_id: str, thread_id: str, path: str) -> FolderContents:
        """The files and folders in `path` (relative to the folder, "" for itself), with those git says were deleted
        there. Raises NotHandedError when the conversation isn't with an agent, and HandedFolderError's others as
        tree.listed."""
        return await tree.listed(await self._handed_root(user_id, thread_id), path)

    async def refresh_handed_folder(self, user_id: str, thread_id: str, folders: list[str]) -> FolderRefresh:
        """The open `folders` of the panel's tree as handed_folder_contents reads each (one that can't be read says why)
        and what git says changed, git asked once. Raises NotHandedError, or MissingPathError for a folder gone."""
        return await tree.refreshed(await self._handed_root(user_id, thread_id), folders)

    async def handed_folder_file(self, user_id: str, thread_id: str, path: str) -> FilePreview:
        """A file's text, as preview.preview. Raises as handed_folder_contents."""
        return await preview.preview(await self._handed_root(user_id, thread_id), path)

    async def handed_folder_changes(self, user_id: str, thread_id: str) -> FolderChanges:
        """What git says changed in the folder. Raises NotHandedError, or MissingPathError for a folder gone."""
        return await changes.changes(await self._handed_root(user_id, thread_id))

    async def handed_folder_diff(self, user_id: str, thread_id: str, path: str) -> FileDiff:
        """What changed in a file git lists as changed, as diff.diff. Raises as handed_folder_contents."""
        return await diff.diff(await self._handed_root(user_id, thread_id), path)

    async def delete_handed_file(self, user_id: str, thread_id: str, path: str) -> None:
        """Moves a file of the folder to the trash, as deleting.delete. Raises DeletingOffError while it's turned off,
        and otherwise as handed_folder_contents."""
        await self._refuse_deleting_while_off()
        await deleting.delete(await self._handed_root(user_id, thread_id), path)

    async def home_folder_contents(self, path: str) -> FolderContents:
        """The files and folders in `path` of the user's home folder, read as handed_folder_contents reads the
        handed one. Raises HandedFolderError's others as contents.contents."""
        return await contents.contents(await _home_root(), path)

    async def home_folder_file(self, path: str) -> FilePreview:
        """A file of the home folder's text, as preview.preview. Raises as home_folder_contents."""
        return await preview.preview(await _home_root(), path)

    async def delete_home_file(self, path: str) -> None:
        """Moves a file of the home folder to the trash, as deleting.delete. Raises as delete_handed_file."""
        await self._refuse_deleting_while_off()
        await deleting.delete(await _home_root(), path)

    async def folder_deleting(self) -> bool:
        """Whether the panel may delete files; off until the user turns it on."""
        return await deleting_setting.allowed(self._storage.store)

    async def set_folder_deleting(self, enabled: bool) -> bool:
        await deleting_setting.allow(self._storage.store, enabled)
        return enabled

    async def _refuse_deleting_while_off(self) -> None:
        if not await self.folder_deleting():
            raise DeletingOffError("Deleting files from the folder panel is turned off in Settings → General.")

    async def _handed_root(self, user_id: str, thread_id: str) -> Path:
        handoff = await handoffs.current(self._storage.store, user_id, thread_id)
        if handoff is None:
            raise NotHandedError("This conversation isn't handed to an agent.")
        return await asyncio.to_thread(paths.root, handoff.folder)


async def _home_root() -> Path:
    return await asyncio.to_thread(lambda: paths.root(str(Path.home())))
