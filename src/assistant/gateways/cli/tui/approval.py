"""Modal that asks the user to approve or reject a tool call."""

from typing import Any

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class ApprovalScreen(ModalScreen[dict[str, Any]]):
    """Returns {"approved": bool, "reason": str | None}."""

    BINDINGS = [Binding("y", "approve", "Approve"), Binding("escape", "reject", "Reject")]

    def __init__(self, request: dict[str, Any]) -> None:
        super().__init__()
        self._request = request

    def compose(self) -> ComposeResult:
        with Vertical(id="approval"):
            yield Static(f"[b]Approve {escape(str(self._request.get('tool')))}?[/b]  [dim]{escape(str(self._request.get('reason')))}[/dim]")
            yield Static(str(self._request.get("command", self._request)), id="approval-command", markup=False)
            yield Input(placeholder="Reason, if you reject (optional)", id="approval-reason")
            with Horizontal(id="approval-buttons"):
                yield Button("Approve (y)", variant="success", id="approve")
                yield Button("Reject (esc)", variant="error", id="reject")

    def on_mount(self) -> None:
        self.query_one("#approve", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_approve() if event.button.id == "approve" else self.action_reject()

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self.action_reject()

    def action_approve(self) -> None:
        self.dismiss({"approved": True, "reason": None})

    def action_reject(self) -> None:
        reason = self.query_one("#approval-reason", Input).value.strip()
        self.dismiss({"approved": False, "reason": reason or None})
