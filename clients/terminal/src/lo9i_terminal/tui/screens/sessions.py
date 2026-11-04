"""The clients connected to the daemon. Updates when one connects or disconnects."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Markdown

from lo9i.client.daemon_client import ClientsApi
from lo9i_terminal.i18n import t
from lo9i_terminal.sessions_text import describe
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable
from lo9i_terminal.tui.section import SettingsSection


class SessionsSection(SettingsSection):
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"clients"})

    def __init__(self, clients: ClientsApi) -> None:
        super().__init__()
        self._clients = clients

    def compose(self) -> ComposeResult:
        with Vertical(id="sessions"):
            with VerticalScroll(id="sessions-scroll"):
                yield Markdown(id="sessions-body")
            with Horizontal(id="sessions-buttons"):
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a client connects or disconnects."""
        clients = await self._clients.list()
        await self.query_one("#sessions-body", Markdown).update(describe(clients, self._clients.own_id))

    def on_button_pressed(self, _: Button.Pressed) -> None:
        self.close()
