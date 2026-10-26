"""The computer the daemon runs on: system, versions and current use, as the web app's Host card. Restarts
or stops the daemon, after asking (daemon/shutdown.py), and checks for and installs a newer version of lo9i
(daemon/updates.py), whose progress comes as `update` events. A restart or stop waiting for runs to end shows
here, whoever asked for it, with Cancel, which takes it back (not the restart an installed update needs), and Now,
which cancels the runs so it goes ahead."""

from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown

from assistant.client.daemon_client import SystemApi
from assistant.protocol import (
    Commit,
    HostStatus,
    NoEndingError,
    PendingEnding,
    StopRefusedError,
    UpdateError,
    UpdateStatus,
)
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen

_RESTART = "Restart the assistant? It stops and starts again once the runs in progress end."
_UPDATE = (
    "Update the assistant? It downloads the new version, installs what it needs and restarts once the runs in "
    "progress end."
)
_NOW = "Cancel the runs in progress so the assistant {does} now? Their replies stop where they are."
_STOP = (
    "Stop the assistant? Jobs, chat channels and the apps stop working until it's started again on the "
    "computer it runs on (opening the terminal app there starts it). It waits for the runs in progress to end."
)


class HostScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"update"})

    def __init__(self, system: SystemApi) -> None:
        super().__init__()
        self._system = system

    def compose(self) -> ComposeResult:
        with Vertical(id="host"):
            yield Markdown("## Host\n\nLoading…", id="host-body")
            with Horizontal(id="host-buttons"):
                yield Button("Refresh", variant="primary", id="refresh")
                yield Button("Check for updates", id="check")
                yield Button("Update", variant="success", id="update", disabled=True)
                yield Button("Restart", variant="warning", id="restart")
                yield Button("Stop", variant="error", id="stop")
                yield Button("Cancel restart", id="take-back")
                yield Button("Now", variant="error", id="now")
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
        # The daemon tells every app it's coming (an `ending` event, AssistantApp.show_ending).
        await self._system.restart()

    @on(Button.Pressed, "#stop")
    @work
    @reports_daemon_unavailable
    async def _stop(self) -> None:
        if not await self.app.push_screen_wait(ConfirmScreen(_STOP, "Stop")):
            return
        try:
            await self._system.stop()
        except StopRefusedError as e:
            self.notify(str(e), severity="error", timeout=15)

    @on(Button.Pressed, "#take-back")
    @reports_daemon_unavailable
    async def _take_back(self) -> None:
        try:
            await self._system.take_back_ending()
        except NoEndingError as e:
            self.notify(str(e), severity="warning")
        await self._refresh()

    @on(Button.Pressed, "#now")
    @work
    @reports_daemon_unavailable
    async def _now(self) -> None:
        pending = await self._system.ending()
        does = "restarts" if pending.ending == "restart" else "stops"
        if not pending.ending or not await self.app.push_screen_wait(ConfirmScreen(_NOW.format(does=does), "Now")):
            return
        try:
            await self._system.end_now()
        except NoEndingError as e:
            self.notify(str(e), severity="warning")

    @on(Button.Pressed, "#check")
    @work
    @reports_daemon_unavailable
    async def _check(self) -> None:
        self.query_one("#check", Button).disabled = True
        try:
            await self._show(await self._system.check_for_update())
        finally:
            self.query_one("#check", Button).disabled = False

    @on(Button.Pressed, "#update")
    @work
    @reports_daemon_unavailable
    async def _update(self) -> None:
        if not await self.app.push_screen_wait(ConfirmScreen(_UPDATE, "Update")):
            return
        try:
            await self._show(await self._system.update())
        except UpdateError as e:
            self.notify(str(e), severity="error", timeout=15)

    async def reload(self) -> None:
        """An update's state changed (an `update` event), or a restart or stop asked for or taken back, or one of
        the runs it waits for ended."""
        await self._refresh()

    @reports_daemon_unavailable
    async def _refresh(self) -> None:
        await self._show(await self._system.update_status())

    async def _show(self, update: UpdateStatus) -> None:
        host, pending = await self._system.host(), await self._system.ending()
        # Before the text: once it says what's new, Update works.
        self.query_one("#update", Button).disabled = not can_install(update)
        take_back = self.query_one("#take-back", Button)
        take_back.label = f"Cancel {pending.ending or 'restart'}"
        take_back.display = can_take_back(pending)
        self.query_one("#now").display = bool(pending.ending and pending.waiting_for_runs)
        await self.query_one("#host-body", Markdown).update(describe(host, update, pending))


def ending_text(does: str, waiting: int, update: bool = False) -> str:
    """When it restarts or stops, as the web app says it (lib/shutdown.ts)."""
    runs = "the run in progress ends" if waiting == 1 else f"the {waiting} runs in progress end"
    waits = [*(["the update being installed is done"] if update else []), *([runs] if waiting else [])]
    return f"The assistant {does} {f'once {" and ".join(waits)}' if waits else 'now'}."


def can_take_back(pending: PendingEnding) -> bool:
    """Something to take back: it waits for runs or an update, and isn't the restart an installed update needs."""
    return (
        bool(pending.ending) and pending.can_take_back and (pending.waiting_for_runs > 0 or pending.waiting_for_update)
    )


def describe(host: HostStatus, update: UpdateStatus | None = None, pending: PendingEnding | None = None) -> str:
    version = f"v{host.version} · {version_text(update.current)}" if update else f"v{host.version}"
    rows = [
        ("OS", host.os),
        ("Arch", host.arch),
        ("Host", host.hostname),
        ("Python", host.python),
        ("lo9i", version),
        ("CPU", f"{host.cpu_cores} cores · {round(host.cpu_percent)}%"),
        ("Memory", _usage(host.memory_used, host.memory_total)),
        ("Disk", _usage(host.disk_used, host.disk_total)),
        ("Uptime", _uptime(host.uptime_seconds)),
    ]
    if host.load_average:
        rows.append(("Load avg", " / ".join(f"{load:.2f}" for load in host.load_average)))
    table = "## Host\n\n| | |\n|---|---|\n" + "\n".join(f"| {term} | {value} |" for term, value in rows)
    return table + (_updates(update) if update else "") + (_pending(pending) if pending and pending.ending else "")


def _pending(pending: PendingEnding) -> str:
    restart = pending.ending == "restart"
    does = "restarts" if restart else "stops"
    said = ending_text(does, pending.waiting_for_runs, pending.waiting_for_update)
    choices = [
        *([f"Cancel {pending.ending} keeps it running."] if can_take_back(pending) else []),
        *(
            [f"An update was installed, so it can't be cancelled: it {does} so the update runs."]
            if not pending.can_take_back
            else []
        ),
        *(["Now cancels the runs."] if pending.waiting_for_runs else []),
    ]
    return f"\n\n### {'Restart' if restart else 'Stop'} pending\n\n{' '.join([said, *choices])}"


def _updates(update: UpdateStatus) -> str:
    new = "".join(f"\n- `{c.sha[:7]}` {c.subject}" for c in update.new) if update.state != "restarting" else ""
    return f"\n\n### Updates\n\n{update_line(update)}\n{new}"


def version_text(commit: Commit | None) -> str:
    """The commit and its day, as the web app's Host card says it (lib/updates.ts)."""
    return f"{commit.sha[:7]} · {commit.date[:10]}" if commit else "unknown"


def update_line(update: UpdateStatus) -> str:
    """Where the update stands, as the web app's Host card says it (lib/updates.ts)."""
    if update.state == "checking":
        return "Checking for updates…"
    if update.state == "updating":
        return f"{update.step}…"
    if update.state == "restarting":
        return "Installed. Restarting once the runs in progress end…"
    if update.state == "failed":
        return update.error
    if update.reason:
        return update.reason
    if not update.checked_at:
        return "Not checked yet."
    if not update.behind:
        return f"Up to date with {update.upstream}."
    return f"{update.behind} new {'change' if update.behind == 1 else 'changes'} on {update.upstream}."


def can_install(update: UpdateStatus) -> bool:
    return update.can_update and update.behind > 0 and update.state in ("idle", "failed")


def _usage(used: int, total: int) -> str:
    return f"{used / 1024**3:.1f} GB / {total / 1024**3:.1f} GB ({used / total * 100:.1f}%)"


def _uptime(seconds: int) -> str:
    days, rest = divmod(seconds, 86400)
    hours, minutes = rest // 3600, rest % 3600 // 60
    return f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"
