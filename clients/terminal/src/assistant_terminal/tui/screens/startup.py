"""Start at boot: turn it on or off from the app. macOS uses LaunchDaemons, Linux a systemd user
service (lo9i-assistant); the text explains the one this daemon's system uses."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown

from assistant.client.daemon_client import SystemApi
from assistant.protocol import StartupError, StartupStatus
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_ABOUT = {
    "macos": """Starting at boot runs the assistant, and Ollama if you use it, from the moment the Mac starts,
without anyone logging in, so scheduled jobs and Telegram keep working. It runs as your user.

- macOS asks for your administrator password once.
- A sleeping or powered-off Mac runs nothing; missed jobs catch up within 6 hours.
- With FileVault on, after a restart nothing runs until someone logs in once.""",
    "linux": """Starting at boot runs the assistant as a systemd user service (`lo9i-assistant`) from the moment
the computer starts, so scheduled jobs and Telegram keep working. It runs as your user.

- Its log: `journalctl --user -u lo9i-assistant -f`
- A powered-off or suspended computer runs nothing; missed jobs catch up within 6 hours.
- Ollama isn't included: its Linux installer runs it as a service of its own.""",
    "unsupported": "Start at boot works on macOS and on Linux with systemd. This system has neither.",
}
_NO_LINGER = """**Without lingering, it runs only while you're logged in.** To start it at boot without
logging in, an administrator runs this once on the computer: `sudo loginctl enable-linger $USER`"""


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
        current = await self._system.startup_status()
        self._message = "Waiting for the macOS password dialog…" if current.platform == "macos" else "Working…"
        await self._show(current)
        try:
            status = await (self._system.enable_startup() if enable else self._system.disable_startup())
            self._message = _done(enable, status)
        except StartupError as e:
            self._message = f"**{e}**"
            status = await self._system.startup_status()
        await self._refresh(status)

    async def _refresh(self, status: StartupStatus) -> None:
        # Controls first, text last: once the text shows the new state, the controls match it.
        supported = status.platform != "unsupported"
        self.query_one("#enable").display = supported and not status.enabled
        self.query_one("#disable").display = supported and status.enabled
        await self._show(status)

    async def _show(self, status: StartupStatus) -> None:
        state = "**on**" + (" (with Ollama)" if status.includes_ollama else "") if status.enabled else "**off**"
        text = f"## Start at boot: {state}\n\n{_ABOUT.get(status.platform, _ABOUT['unsupported'])}"
        if status.platform == "linux" and not status.starts_without_login:
            text += f"\n\n{_NO_LINGER}"
        await self.query_one("#startup-body", Markdown).update(f"{text}\n\n{self._message}" if self._message else text)


def _done(enabled: bool, status: StartupStatus) -> str:
    computer = "the Mac" if status.platform == "macos" else "the computer"
    if not enabled:
        return f"Turned off. The daemon keeps running until you restart {computer} or stop it."
    system = "macOS" if status.platform == "macos" else "systemd"
    return f"Turned on. The assistant restarts under {system} in a few seconds." if not status.managed else "Turned on."
