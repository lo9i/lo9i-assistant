"""Modal for the agent's suggestion to move a focused task out of home (suggest_side_conversation), to
a new side conversation or one that exists."""

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class SideConversationScreen(ModalScreen[dict[str, Any]]):
    """Returns {"moved": bool}. On yes, the app goes to the side conversation (or starts one) once the
    reply ends and sends the brief there."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "stay", "Keep it here")]

    def __init__(self, request: dict[str, Any]) -> None:
        super().__init__()
        self._title = str(request.get("title", ""))
        self._brief = str(request.get("brief", ""))
        self._continues = bool(request.get("thread_id"))
        self._question = "Continue in your side conversation?" if self._continues else "Move to a side conversation?"

    def compose(self) -> ComposeResult:
        with Vertical(id="side-conversation"):
            yield Static(f"{self._question} {self._title}", id="side-conversation-title", markup=False)
            hint = "It goes on there" if self._continues else "It goes on in a conversation of its own"
            yield Static(f"{hint}, starting with this brief.", classes="hint")
            yield Static(self._brief, id="side-conversation-brief", markup=False)
            with Horizontal(id="side-conversation-buttons"):
                yield Button("Move", variant="success", id="move")
                yield Button("Keep it here (esc)", id="stay")

    def on_mount(self) -> None:
        self.query_one("#move", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss({"moved": event.button.id == "move"})

    def action_stay(self) -> None:
        self.dismiss({"moved": False})
