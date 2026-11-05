"""The health check (core/doctor/), as the web app's Health page: the latest report's overview with the starting
context, each cause it found, and the causes marked as known noise. Check now checks today so far in the background;
its report shows when it's saved (a `doctor` event). A cause that's only noise is marked as known, and Not noise
shows it again. Its Setup entry is the setup check (core/setup_check/), as the page's Setup card: Check setup runs it
and lists each part with its fix."""

from pathlib import Path
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from lo9i.client.daemon_client import DoctorApi, OlderDaemonError, SetupCheckApi
from lo9i.core import i18n as core_i18n
from lo9i.core.agent import DoctorPage, SetupReport
from lo9i.core.config import settings
from lo9i.core.setup_check import local
from lo9i_terminal import i18n
from lo9i_terminal.doctor_text import cause_line, describe_cause, describe_known, known_line, overview
from lo9i_terminal.i18n import t
from lo9i_terminal.setup_check_text import markdown
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable
from lo9i_terminal.tui.section import SettingsSection

_OVERVIEW = "overview"
_SETUP = "setup"
_KNOWN = "known:"


class DoctorSection(SettingsSection):
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"doctor"})

    def __init__(self, doctor: DoctorApi, setup: SetupCheckApi, selected: str = _OVERVIEW) -> None:
        """`selected`: the cause to open on (an alert's), else the overview."""
        super().__init__()
        self._doctor = doctor
        self._setup = setup
        self._page: DoctorPage | None = None
        self._report: SetupReport | None = None
        self._selected = selected

    def compose(self) -> ComposeResult:
        with Vertical(id="doctor"):
            yield Static(t("Health check"), id="doctor-title")
            with Horizontal(id="doctor-main"):
                yield OptionList(id="doctor-list")
                yield Static(classes="divider")
                with VerticalScroll(id="doctor-detail"):
                    yield Markdown(id="doctor-body")
            with Horizontal(id="doctor-buttons"):
                yield Button(t("Check now"), variant="primary", id="check")
                yield Button(t("Check setup"), variant="primary", id="check-setup")
                yield Button(t("Mark as known"), id="known")
                yield Button(t("Not noise"), id="forget")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a report is saved or a cause is marked."""
        await self._show(await self._doctor.get())

    async def _show(self, page: DoctorPage) -> None:
        self._page = page
        report = page.report
        options = [Option(t("Overview"), id=_OVERVIEW), Option(t("Setup"), id=_SETUP)]
        options += [Option(cause_line(c), id=c.id) for c in (report.causes if report else [])]
        options += [Option(known_line(k), id=_KNOWN + k.id) for k in page.known]
        ids = [o.id for o in options]
        if self._selected not in ids:
            self._selected = _OVERVIEW
        listed = self.query_one("#doctor-list", OptionList)
        listed.clear_options()
        listed.add_options(options)
        listed.highlighted = ids.index(self._selected)
        checking = self.query_one("#check", Button)
        checking.disabled, checking.label = page.checking, t("Checking…") if page.checking else t("Check now")
        await self._body()

    async def _body(self) -> None:
        page, selected = self._page, self._selected
        report = page.report if page else None
        cause = next((c for c in report.causes if c.id == selected), None) if report else None
        known = next((k for k in page.known if _KNOWN + k.id == selected), None) if page else None
        self.query_one("#known").display = cause is not None
        self.query_one("#forget").display = known is not None
        self.query_one("#check").display = selected != _SETUP
        self.query_one("#check-setup").display = selected == _SETUP
        if selected == _SETUP:
            text = markdown(self._report)
        elif cause is not None:
            text = describe_cause(cause)
        elif known is not None:
            text = describe_known(known)
        else:
            text = overview(report)
        await self.query_one("#doctor-body", Markdown).update(text)

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._selected = event.option.id or _OVERVIEW
        await self._body()

    @on(Button.Pressed, "#check")
    @reports_daemon_unavailable
    async def _check(self) -> None:
        await self._show(await self._doctor.check())

    @on(Button.Pressed, "#check-setup")
    @reports_daemon_unavailable
    async def _check_setup(self) -> None:
        button = self.query_one("#check-setup", Button)
        button.disabled, button.label = True, t("Checking…")
        try:
            self._report = await self._setup_report()
        finally:
            button.disabled, button.label = False, t("Check setup")
        await self._body()

    async def _setup_report(self) -> SetupReport:
        try:
            return await self._setup.run()
        except OlderDaemonError:
            # The rest needs this version's daemon; until it restarts, the check says so.
            older = local.older_daemon(Path(settings.daemon_socket).expanduser())
            return SetupReport([core_i18n.texts(i18n.language()).within(older)])

    @on(Button.Pressed, "#known")
    @reports_daemon_unavailable
    async def _mark_known(self) -> None:
        await self._show(await self._doctor.mark_known(self._selected))

    @on(Button.Pressed, "#forget")
    @reports_daemon_unavailable
    async def _forget(self) -> None:
        await self._show(await self._doctor.forget_known(self._selected.removeprefix(_KNOWN)))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.close()
