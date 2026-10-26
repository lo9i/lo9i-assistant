"""The clients connected to the daemon. Updates when one connects or disconnects."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown

from assistant.client.daemon_client import ClientsApi
from assistant_terminal.sessions_text import describe
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class SessionsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"clients"})

    def __init__(self, clients: ClientsApi) -> None:
        super().__init__()
        self._clients = clients

    def compose(self) -> ComposeResult:
        with Vertical(id="sessions"):
            with VerticalScroll(id="sessions-scroll"):
                yield Markdown(id="sessions-body")
            with Horizontal(id="sessions-buttons"):
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self.query_one("#close", Button).focus()
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a client connects or disconnects."""
        clients = await self._clients.list()
        await self.query_one("#sessions-body", Markdown).update(describe(clients, self._clients.own_id))

    def on_button_pressed(self, _: Button.Pressed) -> None:
        self.dismiss()
