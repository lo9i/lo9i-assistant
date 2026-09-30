"""Connect Telegram without leaving the app: paste a bot token, then pair with a one-time code.

The screen refreshes every few seconds, so it notices when the bot starts and when pairing succeeds.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown

from assistant.client import DaemonClient
from assistant.core.agent import InvalidToken, TelegramStatus
from assistant.gateways.cli.telegram_text import describe

_REFRESH_SECONDS = 2


class TelegramScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, service: DaemonClient) -> None:
        super().__init__()
        self._service = service
        self._error = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="telegram"):
            yield Markdown(id="telegram-body")
            yield Input(placeholder="Bot token", password=True, id="telegram-token")
            with Horizontal(id="telegram-buttons"):
                yield Button("Connect", variant="success", id="connect")
                yield Button("New pairing code", id="pair")
                yield Button("Disconnect", variant="error", id="disconnect")
                yield Button("Close", id="close")

    async def on_mount(self) -> None:
        await self._refresh()
        self.set_interval(_REFRESH_SECONDS, self._refresh)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {"connect": self._connect, "pair": self._pair, "disconnect": self._disconnect}
        if event.button.id == "close":
            self.dismiss()
        else:
            await actions[event.button.id]()

    async def on_input_submitted(self, _: Input.Submitted) -> None:
        await self._connect()

    async def _connect(self) -> None:
        token = self.query_one("#telegram-token", Input).value.strip()
        if not token:
            return
        try:
            await self._service.connect_telegram(token)
            self._error = ""
        except InvalidToken as e:
            self._error = str(e)
        await self._refresh()

    async def _pair(self) -> None:
        await self._service.start_telegram_pairing()
        await self._refresh()

    async def _disconnect(self) -> None:
        await self._service.disconnect_telegram()
        await self._refresh()

    async def _refresh(self) -> None:
        status = await self._service.telegram_status()
        await self.query_one("#telegram-body", Markdown).update(describe(status, self._error))
        self._show(status)

    def _show(self, status: TelegramStatus) -> None:
        self.query_one("#telegram-token").display = not status.connected
        self.query_one("#connect").display = not status.connected
        self.query_one("#pair").display = status.connected and not status.pairing_code
        self.query_one("#disconnect").display = status.connected
