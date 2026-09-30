"""Start at boot: turn the macOS LaunchDaemon on or off from the app."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown

from assistant.client.daemon_client import SystemApi
from assistant.gateways.cli.tui.daemon_errors import reports_daemon_unavailable
from assistant.protocol import StartupError, StartupStatus

_ABOUT = """Starting at boot runs the assistant, and Ollama if you use it, from the moment the Mac starts,
without anyone logging in, so scheduled jobs and Telegram keep working. It runs as your user.

- macOS asks for your administrator password once.
- A sleeping or powered-off Mac runs nothing; missed jobs catch up within 6 hours.
- With FileVault on, after a restart nothing runs until someone logs in once."""


class StartupScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, system: SystemApi) -> None:
        super().__init__()
        self._system = system
        self._message = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="startup"):
            yield Markdown(id="startup-body")
            with Horizontal(id="startup-buttons"):
                yield Button("Enable", variant="success", id="enable")
                yield Button("Disable", variant="error", id="disable")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._refresh(await self._system.startup_status())

    @reports_daemon_unavailable
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss()
            return
        await self._change(enable=event.button.id == "enable")

    async def _change(self, enable: bool) -> None:
        self._message = "Waiting for the macOS password dialog…"
        await self._show(await self._system.startup_status())
        try:
            status = await (self._system.enable_startup() if enable else self._system.disable_startup())
            self._message = _done(enable, status)
        except StartupError as e:
            self._message = f"**{e}**"
            status = await self._system.startup_status()
        await self._refresh(status)

    async def _refresh(self, status: StartupStatus) -> None:
        # Controls first, text last: once the text shows the new state, the controls match it.
        self.query_one("#enable").display = not status.enabled
        self.query_one("#disable").display = status.enabled
        await self._show(status)

    async def _show(self, status: StartupStatus) -> None:
        state = "**on**" + (" (with Ollama)" if status.includes_ollama else "") if status.enabled else "**off**"
        text = f"## Start at boot: {state}\n\n{_ABOUT}"
        await self.query_one("#startup-body", Markdown).update(f"{text}\n\n{self._message}" if self._message else text)


def _done(enabled: bool, status: StartupStatus) -> str:
    if not enabled:
        return "Turned off. The daemon keeps running until you restart the Mac or stop it."
    return "Turned on. The assistant restarts under macOS in a few seconds." if not status.managed else "Turned on."
