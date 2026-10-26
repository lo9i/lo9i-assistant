"""What removed plugins left kept, encrypted on the assistant's computer, to see and delete later: each
plugin's keys while it isn't installed again, and private repositories' tokens nothing needs any more; as
Settings → System's Kept keys card in the web app. Refreshes when plugins change."""

from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import RepositoriesApi
from assistant.core.agent import KeptKeys
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen

_EMPTY = "Nothing kept. Removing a plugin asks whether to keep its keys for installing it again."


def name(kept: KeptKeys) -> str:
    """Its plugin, or the repository whose token is left."""
    return kept.plugin or f"Token for {kept.repository_name}"


def describe(kept: KeptKeys) -> str:
    if not kept.plugin:
        return f"The token for **{kept.repository_name}** ({kept.repository}). No installed plugin needs it."
    keys = "\n".join(f"- `{key}`" for key in kept.keys)
    return f"The keys **{kept.plugin}** was given, used again when it's installed again:\n\n{keys}"


class KeptKeysListScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"mcp", "plugins"})

    def __init__(self, repositories: RepositoriesApi) -> None:
        super().__init__()
        self._repositories = repositories
        self._shown: list[KeptKeys] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="keys"):
            yield Static("Kept keys", id="keys-title")
            with Horizontal(id="keys-main"):
                yield OptionList(id="keys-list")
                yield Static(classes="divider")
                with VerticalScroll(id="keys-detail"):
                    yield Markdown(id="keys-body")
            with Horizontal(id="keys-buttons"):
                yield Button("Delete", variant="error", id="delete")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when plugins change: a removal keeps keys, an install uses them again."""
        self._shown = await self._repositories.kept_keys()
        options = self.query_one("#keys-list", OptionList)
        options.clear_options()
        options.add_options([Option(name(k), id=str(i)) for i, k in enumerate(self._shown)])
        self.query_one("#delete").display = bool(self._shown)
        if self._shown:
            options.highlighted = 0
        await self._show(self._shown[0] if self._shown else None)

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        await self._show(self._selected())

    @on(Button.Pressed, "#delete")
    def _delete(self) -> None:
        kept = self._selected()
        if kept is not None:
            self._confirm_delete(kept)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @work
    @reports_daemon_unavailable
    async def _confirm_delete(self, kept: KeptKeys) -> None:
        what = f"the keys of {kept.plugin}" if kept.plugin else f"the token for {kept.repository_name}"
        again = "Installing it again will ask for them again." if kept.plugin else "Adding it again asks for one."
        if not await self.app.push_screen_wait(ConfirmScreen(f"Delete {what}? {again}", "Delete")):
            return
        await self._repositories.forget_keys(kept)
        self.notify(f"Deleted {what}.")
        await self.reload()

    def _selected(self) -> KeptKeys | None:
        index = self.query_one("#keys-list", OptionList).highlighted
        return self._shown[index] if index is not None and index < len(self._shown) else None

    async def _show(self, kept: KeptKeys | None) -> None:
        await self.query_one("#keys-body", Markdown).update(describe(kept) if kept else _EMPTY)
