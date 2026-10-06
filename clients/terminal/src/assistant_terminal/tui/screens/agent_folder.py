"""Picking the folder a conversation is handed to an agent in (/claude alone), so the user never types a
path: the agents' workspace, the folders used before, or browsing to one from the home folder. Returns
the picked folder's full path, or None."""

from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import ConversationsApi
from assistant.core.agent import AgentFolders, FolderError
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

# Option ids: what Enter does with the option.
_PICK = "pick:"
_BROWSE = "browse:"


class AgentFolderScreen(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]

    def __init__(self, conversations: ConversationsApi, agent_name: str) -> None:
        super().__init__()
        self._conversations = conversations
        self._agent_name = agent_name

    def compose(self) -> ComposeResult:
        with Vertical(id="agent-folder"):
            yield Static(f"Where should {self._agent_name} work?", id="agent-folder-title", markup=False)
            yield Static(id="agent-folder-path", markup=False)
            yield OptionList(id="agent-folder-options")
            with Horizontal(id="agent-folder-buttons"):
                yield Button("Close (esc)", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self._show_offered(await self._conversations.agent_folders())

    @reports_daemon_unavailable
    async def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        chosen = event.option.id or ""
        if chosen.startswith(_PICK):
            self.dismiss(chosen.removeprefix(_PICK))
        elif chosen.startswith(_BROWSE):
            await self._browse(chosen.removeprefix(_BROWSE))

    def on_button_pressed(self, _: Button.Pressed) -> None:
        self.action_close()

    def action_close(self) -> None:
        self.dismiss(None)

    def _show_offered(self, folders: AgentFolders) -> None:
        options = [Option(f"Workspace  {_shown(folders.workspace)}", id=_PICK + folders.workspace)]
        options += [Option(_shown(f), id=_PICK + f) for f in folders.recent]
        options.append(Option("Browse…", id=_BROWSE + folders.home))
        self.query_one("#agent-folder-path", Static).update("Workspace, a folder used before, or browse.")
        self._fill(options)

    async def _browse(self, path: str) -> None:
        try:
            listing = await self._conversations.child_folders(path)
        except FolderError as e:
            self.notify(str(e), severity="error")
            return
        options = [Option("Use this folder", id=_PICK + listing.path)]
        if listing.parent is not None:
            options.append(Option(".. up", id=_BROWSE + listing.parent))
        options += [Option(f"{Path(c).name}/", id=_BROWSE + c) for c in listing.children]
        self.query_one("#agent-folder-path", Static).update(_shown(listing.path))
        self._fill(options)

    def _fill(self, options: list[Option]) -> None:
        shown = self.query_one("#agent-folder-options", OptionList)
        shown.clear_options()
        shown.add_options(options)
        shown.highlighted = 0
        shown.focus()


def _shown(path: str) -> str:
    """With the home folder as ~, shorter to read."""
    home = str(Path.home())
    return "~" + path.removeprefix(home) if path == home or path.startswith(home + "/") else path
