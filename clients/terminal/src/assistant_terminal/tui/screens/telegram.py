"""Connect Telegram without leaving the app: paste a bot token, then pair with a one-time code.

The screen refreshes when the daemon reports a change, so it notices when the bot starts and when
pairing succeeds.
"""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown

from assistant.client.daemon_client import TelegramApi
from assistant.core.agent import InvalidTokenError, TelegramStatus
from assistant_terminal.telegram_text import describe
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class TelegramScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, telegram: TelegramApi) -> None:
        super().__init__()
        self._telegram = telegram
        self._error = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="telegram"):
            yield Markdown(id="telegram-body")
            yield Input(placeholder="Bot token", id="telegram-token")
            with Horizontal(id="telegram-buttons"):
                yield Button("Connect", variant="success", id="connect")
                yield Button("New pairing code", id="pair")
                yield Button("Disconnect", variant="error", id="disconnect")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._refresh()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a change (pairing, bot started or stopped)."""
        await self._refresh()

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @reports_daemon_unavailable
    async def on_input_submitted(self, _: Input.Submitted) -> None:
        await self._connect()

    @on(Button.Pressed, "#connect")
    @reports_daemon_unavailable
    async def _connect(self) -> None:
        token = self.query_one("#telegram-token", Input).value.strip()
        if not token:
            return
        try:
            await self._telegram.connect(token)
            self._error = ""
        except InvalidTokenError as e:
            self._error = str(e)
        await self._refresh()

    @on(Button.Pressed, "#pair")
    @reports_daemon_unavailable
    async def _pair(self) -> None:
        await self._telegram.start_pairing()
        await self._refresh()

    @on(Button.Pressed, "#disconnect")
    @reports_daemon_unavailable
    async def _disconnect(self) -> None:
        await self._telegram.disconnect()
        await self._refresh()

    async def _refresh(self) -> None:
        status = await self._telegram.status()
        # Controls first, text last: once the text shows the new state, the controls match it.
        self._show(status)
        await self.query_one("#telegram-body", Markdown).update(describe(status, self._error))

    def _show(self, status: TelegramStatus) -> None:
        self.query_one("#telegram-token").display = not status.connected
        self.query_one("#connect").display = not status.connected
        self.query_one("#pair").display = status.connected and not status.pairing_code
        self.query_one("#disconnect").display = status.connected
