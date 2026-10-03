"""Connect Slack without leaving the app: copy the app manifest, create the app in Slack, then paste
its three tokens.

The screen refreshes when the daemon reports a change, so it notices when the connection opens.
"""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown

from assistant.client import clipboard
from assistant.client.daemon_client import SlackApi
from assistant.core.agent import SlackError, SlackStatus
from assistant_terminal.slack_text import describe
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

# id: placeholder
_TOKENS = {
    "slack-app-token": "App token (xapp-…)",
    "slack-bot-token": "Bot User OAuth Token (xoxb-…)",
    "slack-user-token": "User OAuth Token (xoxp-…)",
}


class SlackScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, slack: SlackApi) -> None:
        super().__init__()
        self._slack = slack
        self._error = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="slack"):
            yield Markdown(id="slack-body")
            for field_id, placeholder in _TOKENS.items():
                yield Input(placeholder=placeholder, password=True, id=field_id)
            with Horizontal(id="slack-buttons"):
                yield Button("Copy manifest", id="manifest")
                yield Button("Connect", variant="success", id="connect")
                yield Button("Disconnect", variant="error", id="disconnect")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._refresh()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a change (connection opened or closed)."""
        await self._refresh()

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#manifest")
    @reports_daemon_unavailable
    async def _copy_manifest(self) -> None:
        """Through the terminal (OSC 52, reaches the computer in front of you over SSH) and with this
        machine's clipboard command."""
        manifest = await self._slack.manifest()
        self.app.copy_to_clipboard(manifest)
        copied = await clipboard.copy(manifest)
        self.notify("Copied the manifest." if copied else "Sent the manifest to your terminal's clipboard.")

    @reports_daemon_unavailable
    async def on_input_submitted(self, _: Input.Submitted) -> None:
        await self._connect()

    @on(Button.Pressed, "#connect")
    @reports_daemon_unavailable
    async def _connect(self) -> None:
        tokens = [self.query_one(f"#{field_id}", Input).value.strip() for field_id in _TOKENS]
        if not all(tokens):
            self._error = "Paste all three tokens."
        else:
            self._error = await self._try_connect(*tokens)
        await self._refresh()

    @on(Button.Pressed, "#disconnect")
    @reports_daemon_unavailable
    async def _disconnect(self) -> None:
        await self._slack.disconnect()
        await self._refresh()

    async def _try_connect(self, app_token: str, bot_token: str, user_token: str) -> str:
        """The error to show, or an empty string once connected."""
        try:
            await self._slack.connect(app_token, bot_token, user_token)
        except SlackError as e:
            return str(e)
        for field_id in _TOKENS:
            self.query_one(f"#{field_id}", Input).value = ""
        return ""

    async def _refresh(self) -> None:
        status = await self._slack.status()
        # Controls first, text last: once the text shows the new state, the controls match it.
        self._show(status)
        await self.query_one("#slack-body", Markdown).update(describe(status, self._error))

    def _show(self, status: SlackStatus) -> None:
        for field_id in _TOKENS:
            self.query_one(f"#{field_id}").display = not status.connected
        self.query_one("#manifest").display = not status.connected
        self.query_one("#connect").display = not status.connected
        self.query_one("#disconnect").display = status.connected
