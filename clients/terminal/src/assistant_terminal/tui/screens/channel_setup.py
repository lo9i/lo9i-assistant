"""A chat channel's setup in the conversation (its pairing code, its status), when the agent opens it
or right after it's installed from there. The same items as in its details in /plugins."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown

from assistant.client.daemon_client import ChannelsApi
from assistant.core.agent import FoundServer
from assistant_terminal.tui.channel_setup import ChannelSetup
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class ChannelSetupScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"channels"})

    def __init__(self, channels: ChannelsApi, server: FoundServer) -> None:
        super().__init__()
        self._channels, self._server = channels, server

    def compose(self) -> ComposeResult:
        with Vertical(id="channel-setup-dialog"):
            yield Markdown(f"## Set up {self._server.name}\n\n{self._server.description}")
            yield Vertical(id="channel-setup-box")
            with Horizontal(id="channel-setup-buttons"):
                yield Button("Done", variant="success", id="done")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a change: the channel connected, or its items changed."""
        box = self.query_one("#channel-setup-box", Vertical)
        await box.remove_children()
        channel = next((c for c in await self._channels.list() if c.name == self._server.name), None)
        if channel is None:
            await box.mount(Markdown(f"Starting {self._server.name}… its setup shows here once it's running."))
            return
        await box.mount(ChannelSetup(self._channels, channel))

    @on(Button.Pressed, "#done")
    def _done(self) -> None:
        self.dismiss()
