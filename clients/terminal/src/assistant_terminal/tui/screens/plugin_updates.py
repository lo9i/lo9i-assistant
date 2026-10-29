"""The plugins the extras have a newer version of, all picked at first: update the picked ones, or all,
as in the web app's Updates table on Plugins."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, SelectionList, Static

from assistant_terminal.i18n import t
from assistant_terminal.plugins_text import Plugin, update_label


class PluginUpdatesScreen(ModalScreen[list[Plugin] | None]):
    """Returns the plugins to update, None when cancelled."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", t("Cancel"))]

    def __init__(self, newer: list[Plugin]) -> None:
        super().__init__()
        self._newer = newer

    def compose(self) -> ComposeResult:
        with Vertical(id="plugin-updates"):
            yield Static(t("Updates: {count} plugins have a newer version in the extras.", count=len(self._newer)))
            yield Static(t("Space unpicks the ones to leave as they are."), classes="hint")
            yield SelectionList[str](*[(update_label(p), p.key, True) for p in self._newer], id="plugin-updates-list")
            with Horizontal(id="plugin-updates-buttons"):
                yield Button(t("Update selected"), variant="success", id="update-selected")
                yield Button(t("Update all"), id="update-all")
                yield Button(t("Cancel (esc)"), id="cancel")

    def on_mount(self) -> None:
        self.query_one("#plugin-updates-list").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "update-all":
            self.dismiss(self._newer)
        elif event.button.id == "update-selected":
            picked = set(self.query_one("#plugin-updates-list", SelectionList).selected)
            self.dismiss([p for p in self._newer if p.key in picked])
        else:
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)
