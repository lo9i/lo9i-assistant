"""The computer the daemon runs on: system, versions and current use, as the web app's Host card. Restarts
or stops the daemon, after asking (daemon/shutdown.py)."""

from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown

from assistant.client.daemon_client import SystemApi
from assistant.protocol import HostStatus, StopRefusedError
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen

_RESTART = "Restart the assistant? It stops and starts again once the runs in progress end."
_STOP = (
    "Stop the assistant? Jobs, chat channels and the apps stop working until it's started again on the "
    "computer it runs on (opening the terminal app there starts it). It waits for the runs in progress to end."
)


class HostScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, system: SystemApi) -> None:
        super().__init__()
        self._system = system

    def compose(self) -> ComposeResult:
        with Vertical(id="host"):
            yield Markdown("## Host\n\nLoading…", id="host-body")
            with Horizontal(id="host-buttons"):
                yield Button("Refresh", variant="primary", id="refresh")
                yield Button("Restart", variant="warning", id="restart")
                yield Button("Stop", variant="error", id="stop")
                yield Button("Close", id="close")

    async def on_mount(self) -> None:
        await self._refresh()

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#refresh")
    async def _refresh_pressed(self) -> None:
        await self._refresh()

    @on(Button.Pressed, "#restart")
    @work
    @reports_daemon_unavailable
    async def _restart(self) -> None:
        if not await self.app.push_screen_wait(ConfirmScreen(_RESTART, "Restart")):
            return
        waiting = (await self._system.restart()).waiting_for_runs
        self.notify(_ending("restarts", waiting), timeout=10)

    @on(Button.Pressed, "#stop")
    @work
    @reports_daemon_unavailable
    async def _stop(self) -> None:
        if not await self.app.push_screen_wait(ConfirmScreen(_STOP, "Stop")):
            return
        try:
            waiting = (await self._system.stop()).waiting_for_runs
        except StopRefusedError as e:
            self.notify(str(e), severity="error", timeout=15)
            return
        self.notify(_ending("stops", waiting), timeout=10)

    @reports_daemon_unavailable
    async def _refresh(self) -> None:
        await self.query_one("#host-body", Markdown).update(describe(await self._system.host()))


def _ending(does: str, waiting: int) -> str:
    if not waiting:
        return f"The assistant {does} now."
    runs = "the run in progress ends" if waiting == 1 else f"the {waiting} runs in progress end"
    return f"The assistant {does} once {runs}."


def describe(host: HostStatus) -> str:
    rows = [
        ("OS", host.os),
        ("Arch", host.arch),
        ("Host", host.hostname),
        ("Python", host.python),
        ("lo9i", f"v{host.version}"),
        ("CPU", f"{host.cpu_cores} cores · {round(host.cpu_percent)}%"),
        ("Memory", _usage(host.memory_used, host.memory_total)),
        ("Disk", _usage(host.disk_used, host.disk_total)),
        ("Uptime", _uptime(host.uptime_seconds)),
    ]
    if host.load_average:
        rows.append(("Load avg", " / ".join(f"{load:.2f}" for load in host.load_average)))
    return "## Host\n\n| | |\n|---|---|\n" + "\n".join(f"| {term} | {value} |" for term, value in rows)


def _usage(used: int, total: int) -> str:
    return f"{used / 1024**3:.1f} GB / {total / 1024**3:.1f} GB ({used / total * 100:.1f}%)"


def _uptime(seconds: int) -> str:
    days, rest = divmod(seconds, 86400)
    hours, minutes = rest // 3600, rest % 3600 // 60
    return f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"
