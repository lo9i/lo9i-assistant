"""The bash sandbox (Settings → General, /sandbox): whether the assistant's commands run in a container."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Markdown

from lo9i.client.daemon_client import SandboxApi
from lo9i.core.agent import SandboxStatus, SandboxUnavailableError
from lo9i_terminal.i18n import t
from lo9i_terminal.sandbox_text import describe
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable
from lo9i_terminal.tui.section import SettingsSection


class SandboxSection(SettingsSection):
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"settings"})

    def __init__(self, sandbox: SandboxApi) -> None:
        super().__init__()
        self._sandbox = sandbox
        self._error = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="sandbox"):
            yield Markdown(id="sandbox-body")
            with Horizontal(id="sandbox-buttons"):
                yield Button(t("Turn on"), variant="success", id="sandbox-on")
                yield Button(t("Turn off"), id="sandbox-off")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._show(await self._sandbox.status())

    @reports_daemon_unavailable
    async def reload(self) -> None:
        await self._show(await self._sandbox.status())

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.close()

    @on(Button.Pressed, "#sandbox-on")
    @reports_daemon_unavailable
    async def _turn_on(self) -> None:
        self.query_one("#sandbox-on", Button).disabled = True
        await self.query_one("#sandbox-body", Markdown).update(t("Turning on… downloading the image."))
        try:
            status, self._error = await self._sandbox.set_enabled(True), ""
        except SandboxUnavailableError as e:
            status, self._error = await self._sandbox.status(), str(e)
        await self._show(status)

    @on(Button.Pressed, "#sandbox-off")
    @reports_daemon_unavailable
    async def _turn_off(self) -> None:
        self._error = ""
        await self._show(await self._sandbox.set_enabled(False))

    async def _show(self, status: SandboxStatus) -> None:
        on_button = self.query_one("#sandbox-on", Button)
        on_button.display, on_button.disabled = not status.enabled, not status.available
        self.query_one("#sandbox-off").display = status.enabled
        await self.query_one("#sandbox-body", Markdown).update(describe(status, self._error))
