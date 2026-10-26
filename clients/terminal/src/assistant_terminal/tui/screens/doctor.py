"""The health check (core/doctor/), as the web app's Health page: the latest report's overview with the starting
context, each cause it found, and the causes marked as known noise. Check now checks today so far in the background;
its report shows when it's saved (a `doctor` event). A cause that's only noise is marked as known, and Not noise
shows it again."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import DoctorApi
from assistant.core.agent import DoctorPage
from assistant_terminal.doctor_text import cause_line, describe_cause, describe_known, known_line, overview
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_OVERVIEW = "overview"
_KNOWN = "known:"


class DoctorScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"doctor"})

    def __init__(self, doctor: DoctorApi) -> None:
        super().__init__()
        self._doctor = doctor
        self._page: DoctorPage | None = None
        self._selected = _OVERVIEW

    def compose(self) -> ComposeResult:
        with Vertical(id="doctor"):
            yield Static("Health check", id="doctor-title")
            with Horizontal(id="doctor-main"):
                yield OptionList(id="doctor-list")
                yield Static(classes="divider")
                with VerticalScroll(id="doctor-detail"):
                    yield Markdown(id="doctor-body")
            with Horizontal(id="doctor-buttons"):
                yield Button("Check now", variant="primary", id="check")
                yield Button("Mark as known", id="known")
                yield Button("Not noise", id="forget")
                yield Button("Close", id="close")

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
        options = [Option("Overview", id=_OVERVIEW)]
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
        checking.disabled, checking.label = page.checking, "Checking…" if page.checking else "Check now"
        await self._body()

    async def _body(self) -> None:
        page, selected = self._page, self._selected
        report = page.report if page else None
        cause = next((c for c in report.causes if c.id == selected), None) if report else None
        known = next((k for k in page.known if _KNOWN + k.id == selected), None) if page else None
        self.query_one("#known").display = cause is not None
        self.query_one("#forget").display = known is not None
        if cause is not None:
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
        self.dismiss(None)
