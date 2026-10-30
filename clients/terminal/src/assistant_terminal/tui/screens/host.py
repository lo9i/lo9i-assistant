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
from assistant_terminal.i18n import decimal, t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen

_RESTART = translatable("Restart the assistant? It stops and starts again once the runs in progress end.")
_UPDATE = translatable(
    "Update the assistant? It downloads the new version, installs what it needs and restarts once the runs in "
    "progress end."
)
_NOW_RESTART = translatable(
    "Cancel the runs in progress so the assistant restarts now? Their replies stop where they are."
)
_NOW_STOP = translatable("Cancel the runs in progress so the assistant stops now? Their replies stop where they are.")
_STOP = translatable(
    "Stop the assistant? Jobs, chat channels and the apps stop working until it's started again on the "
    "computer it runs on (opening the terminal app there starts it). It waits for the runs in progress to end."
)


class HostScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", translatable("Close"))]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"update"})

    def __init__(self, system: SystemApi) -> None:
        super().__init__()
        self._system = system

    def compose(self) -> ComposeResult:
        with Vertical(id="host"):
            yield Markdown("## " + t("Host") + "\n\n" + t("Loading…"), id="host-body")
            with Horizontal(id="host-buttons"):
                yield Button(t("Refresh"), variant="primary", id="refresh")
                yield Button(t("Check for updates"), id="check")
                yield Button(t("Update"), variant="success", id="update", disabled=True)
                yield Button(t("Restart"), variant="warning", id="restart")
                yield Button(t("Stop"), variant="error", id="stop")
                yield Button(t("Cancel restart"), id="take-back")
                yield Button(t("Now"), variant="error", id="now")
                yield Button(t("Close"), id="close")

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
        if not await self.app.push_screen_wait(ConfirmScreen(t(_RESTART), t("Restart"))):
            return
        # The daemon tells every app it's coming (an `ending` event, AssistantApp.show_ending).
        await self._system.restart()

    @on(Button.Pressed, "#stop")
    @work
    @reports_daemon_unavailable
    async def _stop(self) -> None:
        if not await self.app.push_screen_wait(ConfirmScreen(t(_STOP), t("Stop"))):
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
        question = t(_NOW_RESTART) if pending.ending == "restart" else t(_NOW_STOP)
        if not pending.ending or not await self.app.push_screen_wait(ConfirmScreen(question, t("Now"))):
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
        if not await self.app.push_screen_wait(ConfirmScreen(t(_UPDATE), t("Update"))):
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
        take_back.label = t("Cancel stop") if pending.ending == "stop" else t("Cancel restart")
        take_back.display = can_take_back(pending)
        self.query_one("#now").display = bool(pending.ending and pending.waiting_for_runs)
        stop = self.query_one("#stop", Button)
        stop.disabled, stop.tooltip = bool(host.stop_refusal), host.stop_refusal or None
        await self.query_one("#host-body", Markdown).update(describe(host, update, pending))


def ending_text(does: str, waiting: int, update: bool = False) -> str:
    """When it restarts or stops (`does` is "restarts" or "stops"), as the web app says it (lib/shutdown.ts)."""
    runs = t("the run in progress ends") if waiting == 1 else t("the {count} runs in progress end", count=waiting)
    waits = [*([t("the update being installed is done")] if update else []), *([runs] if waiting else [])]
    when = t("once {waits}", waits=t(" and ").join(waits)) if waits else t("now")
    return (
        t("The assistant restarts {when}.", when=when)
        if does == "restarts"
        else t("The assistant stops {when}.", when=when)
    )


def can_take_back(pending: PendingEnding) -> bool:
    """Something to take back: it waits for runs or an update, and nothing needs it (an update installed)."""
    return (
        bool(pending.ending) and pending.can_take_back and (pending.waiting_for_runs > 0 or pending.waiting_for_update)
    )


def describe(host: HostStatus, update: UpdateStatus | None = None, pending: PendingEnding | None = None) -> str:
    version = f"v{host.version} · {version_text(update.current)}" if update else f"v{host.version}"
    rows = [
        (t("OS"), host.os),
        (t("Arch"), host.arch),
        (t("Host"), host.hostname),
        ("Python", host.python),
        ("lo9i", version),
        ("CPU", t("{cores} cores · {percent}%", cores=host.cpu_cores, percent=round(host.cpu_percent))),
        (t("Memory"), _usage(host.memory_used, host.memory_total)),
        (t("Disk"), _usage(host.disk_used, host.disk_total)),
        (t("Uptime"), _uptime(host.uptime_seconds)),
    ]
    if host.load_average:
        rows.append((t("Load avg"), " / ".join(f"{load:.2f}" for load in host.load_average)))
    table = "## " + t("Host") + "\n\n| | |\n|---|---|\n" + "\n".join(f"| {term} | {value} |" for term, value in rows)
    if host.stop_refusal:
        table += "\n\n" + t("Stop: {reason}", reason=host.stop_refusal)
    return table + (_updates(update) if update else "") + (_pending(pending) if pending and pending.ending else "")


def _pending(pending: PendingEnding) -> str:
    restart = pending.ending == "restart"
    said = ending_text("restarts" if restart else "stops", pending.waiting_for_runs, pending.waiting_for_update)
    cancel = t("Cancel restart keeps it running.") if restart else t("Cancel stop keeps it running.")
    choices = [
        *([cancel] if can_take_back(pending) else []),
        *(
            [t("{needed_by}, so it can't be cancelled.", needed_by=pending.needed_by or t("Something needs it"))]
            if not pending.can_take_back
            else []
        ),
        *([t("Now cancels the runs.")] if pending.waiting_for_runs else []),
    ]
    heading = t("Restart pending") if restart else t("Stop pending")
    return f"\n\n### {heading}\n\n{' '.join([said, *choices])}"


def _updates(update: UpdateStatus) -> str:
    new = "".join(f"\n- `{c.sha[:7]}` {c.subject}" for c in update.new) if update.state != "restarting" else ""
    return "\n\n### " + t("Updates") + f"\n\n{update_line(update)}\n{new}"


def version_text(commit: Commit | None) -> str:
    """The commit and its day, as the web app's Host card says it (lib/updates.ts)."""
    return f"{commit.sha[:7]} · {commit.date[:10]}" if commit else t("unknown")


def update_line(update: UpdateStatus) -> str:
    """Where the update stands, as the web app's Host card says it (lib/updates.ts)."""
    if update.state == "checking":
        return t("Checking for updates…")
    if update.state == "updating":
        return f"{update.step}…"
    if update.state == "restarting":
        return t("Installed. Restarting once the runs in progress end…")
    if update.state == "failed":
        return update.error
    if update.reason:
        return update.reason
    if not update.checked_at:
        return t("Not checked yet.")
    if not update.behind:
        return t("Up to date with {upstream}.", upstream=update.upstream)
    if update.behind == 1:
        return t("1 new change on {upstream}.", upstream=update.upstream)
    return t("{count} new changes on {upstream}.", count=update.behind, upstream=update.upstream)


def can_install(update: UpdateStatus) -> bool:
    return update.can_update and update.behind > 0 and update.state in ("idle", "failed")


def _usage(used: int, total: int) -> str:
    return f"{decimal(used / 1024**3)} GB / {decimal(total / 1024**3)} GB ({decimal(used / total * 100)}%)"


def _uptime(seconds: int) -> str:
    days, rest = divmod(seconds, 86400)
    hours, minutes = rest // 3600, rest % 3600 // 60
    values = {"days": days, "hours": hours, "minutes": minutes}
    return t("{days}d {hours}h {minutes}m", **values) if days else t("{hours}h {minutes}m", **values)
