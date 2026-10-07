"""Asked after a plugin is removed: its keys (and its private repository's token, when nothing else
needs it) stay encrypted, for installing it again, unless the user deletes them; as the web app's
question. Keep has the focus, so Enter or Escape alone keeps them."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Static

from assistant.client.daemon_client import RepositoriesApi
from assistant.core.agent import KeptKeys


class KeptKeysScreen(ModalScreen[bool]):
    """Returns True to delete them."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "keep", "Keep")]

    def __init__(self, kept: KeptKeys) -> None:
        super().__init__()
        self._kept = kept

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm"):
            yield Static(question(self._kept), id="confirm-question", markup=False)
            with Horizontal(id="confirm-buttons"):
                yield Button("Keep (esc)", variant="primary", id="keep")
                yield Button("Delete", variant="error", id="delete")

    def on_mount(self) -> None:
        self.query_one("#keep", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "delete")

    def action_keep(self) -> None:
        self.dismiss(False)


def question(kept: KeptKeys) -> str:
    parts = [*kept.keys, *([f"the token for {kept.repository_name}"] if kept.repository else [])]
    named = f"{', '.join(parts[:-1])} and {parts[-1]}" if len(parts) > 1 else parts[0]
    return (
        f"Keep the keys of {kept.plugin}? {named} {'are' if len(parts) > 1 else 'is'} kept encrypted on this"
        " computer, and used when you install it again."
    )


async def ask_about_keys(screen: Screen, repositories: RepositoriesApi, kept: KeptKeys | None) -> None:
    """After a removal: asks, and deletes them when the user says so. Call it from a worker."""
    if kept is None or not await screen.app.push_screen_wait(KeptKeysScreen(kept)):
        return
    await repositories.forget_keys(kept)
    screen.notify(f"Deleted the keys of {kept.plugin}.")
