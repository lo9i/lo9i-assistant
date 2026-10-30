"""Start at boot: turn it on or off from the app. macOS uses LaunchDaemons, Linux a systemd user
service (lo9i-assistant); the text explains the one this daemon's system uses. One installed by an older
version says how it differs, and Install again replaces it."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown

from assistant.client.daemon_client import SystemApi
from assistant.protocol import StartupError, StartupStatus
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_ABOUT = {
    "macos": translatable(
        "Starting at boot runs the assistant, and Ollama if you use it, from the moment the Mac starts, without "
        "anyone logging in, so scheduled jobs and Telegram keep working. It runs as your user.\n\n"
        "- macOS asks for your administrator password once.\n"
        "- A sleeping or powered-off Mac runs nothing; missed jobs catch up within 6 hours, and /notifications says "
        "when one ran late or was missed.\n"
        "- With FileVault on, after a restart nothing runs until someone logs in once."
    ),
    "linux": translatable(
        "Starting at boot runs the assistant as a systemd user service (`lo9i-assistant`) from the moment the "
        "computer starts, so scheduled jobs and Telegram keep working. It runs as your user.\n\n"
        "- Its log: `/logs`; output from before it starts logging: `journalctl --user -u lo9i-assistant`\n"
        "- A powered-off or suspended computer runs nothing; missed jobs catch up within 6 hours, and /notifications "
        "says when one ran late or was missed.\n"
        "- Ollama isn't included: its Linux installer runs it as a service of its own."
    ),
    "unsupported": translatable("Start at boot works on macOS and on Linux with systemd. This system has neither."),
}
_NO_LINGER = translatable(
    "**Without lingering, it runs only while you're logged in.** To start it at boot without logging in, an "
    "administrator runs this once on the computer: `sudo loginctl enable-linger $USER`"
)


class StartupScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", translatable("Close"))]

    def __init__(self, system: SystemApi) -> None:
        super().__init__()
        self._system = system
        self._message = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="startup"):
            yield Markdown(id="startup-body")
            with Horizontal(id="startup-buttons"):
                yield Button(t("Enable"), variant="success", id="enable")
                yield Button(t("Disable"), variant="error", id="disable")
                yield Button(t("Install again"), variant="primary", id="reinstall")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._refresh(await self._system.startup_status())

    @reports_daemon_unavailable
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss()
            return
        if event.button.id == "reinstall":
            await self._reinstall()
            return
        await self._change(enable=event.button.id == "enable")

    async def _reinstall(self) -> None:
        self._message = t("Waiting for the macOS password dialog…")
        await self._show(await self._system.startup_status())
        try:
            status = await self._system.reinstall_startup()
            self._message = _reinstalled(status)
        except StartupError as e:
            self._message = f"**{e}**"
            status = await self._system.startup_status()
        await self._refresh(status)

    async def _change(self, enable: bool) -> None:
        current = await self._system.startup_status()
        self._message = t("Waiting for the macOS password dialog…") if current.platform == "macos" else t("Working…")
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
        self.query_one("#reinstall").display = status.enabled and bool(status.outdated)
        await self._show(status)

    async def _show(self, status: StartupStatus) -> None:
        if status.enabled:
            state = "**" + t("on") + "**" + (" " + t("(with Ollama)") if status.includes_ollama else "")
        else:
            state = "**" + t("off") + "**"
        about = t(_ABOUT.get(status.platform, _ABOUT["unsupported"]))
        text = "## " + t("Start at boot: {state}", state=state) + f"\n\n{about}"
        if status.platform == "linux" and not status.starts_without_login:
            text += f"\n\n{t(_NO_LINGER)}"
        if status.enabled and status.outdated:
            reasons = "\n".join(f"- {why}" for why in status.outdated)
            older = t("It was installed by an older version.")
            text += f"\n\n**{older}** " + t("Install again fixes this:") + f"\n\n{reasons}"
        await self.query_one("#startup-body", Markdown).update(f"{text}\n\n{self._message}" if self._message else text)


def _reinstalled(status: StartupStatus) -> str:
    if status.managed:
        return t("Installed again. The assistant restarts once the runs in progress end.")
    return t("Installed again. The assistant restarts under macOS in a few seconds.")


def _done(enabled: bool, status: StartupStatus) -> str:
    computer = t("the Mac") if status.platform == "macos" else t("the computer")
    if not enabled:
        return t("Turned off. The daemon keeps running until you restart {computer} or stop it.", computer=computer)
    system = "macOS" if status.platform == "macos" else "systemd"
    if status.managed:
        return t("Turned on.")
    return t("Turned on. The assistant restarts under {system} in a few seconds.", system=system)
