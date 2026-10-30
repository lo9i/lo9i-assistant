"""Picking the folder a conversation is handed to an agent in from the plain REPL (/claude alone), as the full
app's picker does (tui/screens/agent_folder.py): the agents' workspace, the folders used before, or browsing to
one from the home folder, hidden folders (named with a dot) only after Show hidden. Every choice is a number,
so it reads the same in every language; a full path picks that folder, and nothing cancels."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from assistant.core.agent import AgentFolders, FolderError, FolderListing
from assistant_terminal.i18n import t
from assistant_terminal.style import YELLOW, paint

# Reads a line after showing the prompt; None at the end of input.
Read = Callable[[str], Awaitable[str | None]]


class Folders(Protocol):
    async def agent_folders(self) -> AgentFolders: ...
    async def child_folders(self, path: str, hidden: bool = False) -> FolderListing: ...


@dataclass(frozen=True)
class _Choice:
    label: str
    folder: str
    # Browses `folder` instead of picking it, showing hidden folders when `hidden`.
    browse: bool = False
    hidden: bool = False


class FolderPrompt:
    def __init__(self, folders: Folders, read: Read) -> None:
        self._folders = folders
        self._read = read

    async def pick(self, agent_name: str) -> str | None:
        """The picked folder's full path, or None when cancelled."""
        print(paint(YELLOW, "\n" + t("Where should {agent} work?", agent=agent_name)))
        choices = _offered(await self._folders.agent_folders())
        while True:
            print("\n".join(f"  {number}. {c.label}" for number, c in enumerate(choices, 1)))
            answer = (await self._read(t("[a number or a full path, or Enter to cancel] ")) or "").strip()
            choice = _numbered(choices, answer)
            if choice is None:
                return answer or None
            if not choice.browse:
                return choice.folder
            choices = await self._browse(choice, choices)

    async def _browse(self, choice: _Choice, current: list[_Choice]) -> list[_Choice]:
        """The choices inside the folder; the current ones again when it can't be read."""
        try:
            listing = await self._folders.child_folders(choice.folder, choice.hidden)
        except FolderError as e:
            print(e)
            return current
        print(paint(YELLOW, listing.path))
        return _listed(listing, choice.hidden)


def _offered(folders: AgentFolders) -> list[_Choice]:
    workspace = _Choice(folders.workspace + t(" (workspace)"), folders.workspace)
    recent = [_Choice(folder, folder) for folder in folders.recent]
    return [workspace, *recent, _Choice(t("Browse…"), folders.home, browse=True)]


def _listed(listing: FolderListing, hidden: bool) -> list[_Choice]:
    """This folder, up, showing or hiding hidden folders, then the folders inside."""
    choices = [_Choice(t("Use this folder"), listing.path)]
    if listing.parent is not None:
        choices.append(_Choice(t(".. up"), listing.parent, browse=True, hidden=hidden))
    toggle = t("Hide hidden") if hidden else t("Show hidden")
    choices.append(_Choice(toggle, listing.path, browse=True, hidden=not hidden))
    return choices + [_Choice(f"{Path(c).name}/", c, browse=True, hidden=hidden) for c in listing.children]


def _numbered(choices: list[_Choice], answer: str) -> _Choice | None:
    if answer.isdigit() and 1 <= int(answer) <= len(choices):
        return choices[int(answer) - 1]
    return None
