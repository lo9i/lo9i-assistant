"""The computer the daemon runs on: system, versions and current use, as the web app's Host card."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown

from assistant.client.daemon_client import SystemApi
from assistant.protocol import HostStatus
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


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
                yield Button("Close", id="close")

    async def on_mount(self) -> None:
        await self._refresh()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss()
            return
        await self._refresh()

    @reports_daemon_unavailable
    async def _refresh(self) -> None:
        await self.query_one("#host-body", Markdown).update(describe(await self._system.host()))


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
