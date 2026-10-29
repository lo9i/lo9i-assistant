"""Asks before something that can't be undone, such as deleting a job or a skill. Cancel has the
focus, so Enter alone never deletes anything."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Static

from assistant_terminal.i18n import t


class ConfirmScreen(ModalScreen[bool]):
    """Returns True when the user confirms."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("y", "confirm", t("Confirm")),
        Binding("escape", "cancel", t("Cancel")),
    ]

    def __init__(self, question: str, action: str) -> None:
        super().__init__()
        self._question = question
        self._action = action

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm"):
            yield Static(self._question, id="confirm-question", markup=False)
            with Horizontal(id="confirm-buttons"):
                yield Button(f"{self._action} (y)", variant="error", id="confirm-yes")
                yield Button(t("Cancel (esc)"), id="confirm-no")

    def on_mount(self) -> None:
        self.query_one("#confirm-no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class ConfirmWithOptionScreen(ModalScreen[bool | None]):
    """Like ConfirmScreen, with a checkbox, unchecked at first. Returns None when cancelled, else
    whether the box was checked."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", t("Cancel"))]

    def __init__(self, question: str, action: str, option: str) -> None:
        super().__init__()
        self._question, self._action, self._option = question, action, option

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm"):
            yield Static(self._question, id="confirm-question", markup=False)
            yield Checkbox(self._option, value=False, id="confirm-option")
            with Horizontal(id="confirm-buttons"):
                yield Button(self._action, variant="error", id="confirm-yes")
                yield Button(t("Cancel (esc)"), id="confirm-no")

    def on_mount(self) -> None:
        self.query_one("#confirm-no", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-yes":
            self.dismiss(self.query_one("#confirm-option", Checkbox).value)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
