"""The briefing, as the web app's Briefing page: the latest briefing and review, the open loops (Done, Dismiss, Stop
suggesting its kind), the kinds muted (Suggest again), and the settings: each feature on or off, the briefing's and the
nightly review's times and the weekly review's day. Brief me now writes and sends the briefing in the background; the
screen shows it when it's saved (a `proactive` event)."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Markdown, OptionList, Select, Static, Switch
from textual.widgets.option_list import Option

from assistant.client.daemon_client import ProactiveApi
from assistant.core.agent import ProactivePage, ProactiveSettings
from assistant_terminal.briefing_text import describe_loop, loop_line, overview
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.page import PageScreen

_OVERVIEW = "overview"
_SETTINGS = "settings"
_LOOP = "loop:"
_MUTED = "muted:"
_SWITCHES = (
    ("briefing", translatable("Morning briefing")),
    ("nightly", translatable("Nightly review")),
    ("weekly", translatable("Weekly review")),
    ("reminders", translatable("Urgent reminders")),
)
_DAYS = (
    translatable("Monday"),
    translatable("Tuesday"),
    translatable("Wednesday"),
    translatable("Thursday"),
    translatable("Friday"),
    translatable("Saturday"),
    translatable("Sunday"),
)


class BriefingScreen(PageScreen[None]):
    PAGE = "briefing"
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", translatable("Close"))]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"proactive"})

    def __init__(self, proactive: ProactiveApi) -> None:
        super().__init__()
        self._proactive = proactive
        self._page: ProactivePage | None = None
        self._selected = _OVERVIEW

    def compose_page(self) -> ComposeResult:
        with Vertical(id="briefing"):
            yield Static(t("Briefing"), id="briefing-title")
            with Horizontal(id="briefing-main"):
                yield OptionList(id="briefing-list")
                yield Static(classes="divider")
                with VerticalScroll(id="briefing-detail"):
                    yield Markdown(id="briefing-body")
                    with Vertical(id="briefing-settings"):
                        for key, label in _SWITCHES:
                            with Horizontal(classes="briefing-row"):
                                yield Switch(id=f"switch-{key}")
                                yield Label(t(label))
                        yield Label(t("Briefing time (HH:MM, Enter to save)"))
                        yield Input(id="briefing-time")
                        yield Label(t("Nightly review time (HH:MM, Enter to save)"))
                        yield Input(id="nightly-time")
                        yield Label(t("Weekly review day"))
                        yield Select([(t(d), n) for n, d in enumerate(_DAYS)], allow_blank=False, id="weekly-day")
            with Horizontal(id="briefing-buttons"):
                yield Button(t("Brief me now"), variant="primary", id="brief")
                yield Button(t("Done"), id="done")
                yield Button(t("Dismiss"), id="dismiss")
                yield Button(t("Stop suggesting"), id="stop")
                yield Button(t("Suggest again"), id="unmute")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a briefing, review, loop or setting is saved."""
        await self._show(await self._proactive.get())

    async def _show(self, page: ProactivePage) -> None:
        self._page = page
        options = [Option(t("Overview"), id=_OVERVIEW), Option(t("Settings"), id=_SETTINGS)]
        options += [Option(loop_line(o), id=_LOOP + o.id) for o in page.loops if o.status == "open"]
        options += [Option(t("Muted: {kind}", kind=k), id=_MUTED + k) for k in page.settings.muted]
        ids = [o.id for o in options]
        self._selected = self._selected if self._selected in ids else _OVERVIEW
        listed = self.query_one("#briefing-list", OptionList)
        listed.clear_options()
        listed.add_options(options)
        listed.highlighted = ids.index(self._selected)
        briefing = self.query_one("#brief", Button)
        briefing.disabled = "briefing" in page.running
        briefing.label = t("Writing…") if briefing.disabled else t("Brief me now")
        self._fill_settings(page.settings)
        await self._body()

    def _fill_settings(self, chosen: ProactiveSettings) -> None:
        for key, _ in _SWITCHES:
            with self.query_one(f"#switch-{key}", Switch).prevent(Switch.Changed):
                self.query_one(f"#switch-{key}", Switch).value = getattr(chosen, key)
        self.query_one("#briefing-time", Input).value = chosen.briefing_time
        self.query_one("#nightly-time", Input).value = chosen.nightly_time
        with self.query_one("#weekly-day", Select).prevent(Select.Changed):
            self.query_one("#weekly-day", Select).value = chosen.weekly_day

    async def _body(self) -> None:
        page, selected = self._page, self._selected
        loop = next((o for o in page.loops if _LOOP + o.id == selected), None) if page else None
        for button in ("#done", "#dismiss"):
            self.query_one(button).display = loop is not None
        self.query_one("#stop").display = loop is not None and bool(loop.kind)
        self.query_one("#unmute").display = selected.startswith(_MUTED)
        self.query_one("#briefing-settings").display = selected == _SETTINGS
        body = self.query_one("#briefing-body", Markdown)
        body.display = selected != _SETTINGS
        if loop is not None:
            await body.update(describe_loop(loop))
        elif selected.startswith(_MUTED):
            await body.update(t("Not suggested any more: {kind}.", kind=selected.removeprefix(_MUTED)))
        elif page is not None:
            await body.update(overview(page))

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._selected = event.option.id or _OVERVIEW
        await self._body()

    @on(Switch.Changed)
    @reports_daemon_unavailable
    async def _switched(self, event: Switch.Changed) -> None:
        key = (event.switch.id or "").removeprefix("switch-")
        await self._save({key: event.value})

    @on(Input.Submitted, "#briefing-time")
    @reports_daemon_unavailable
    async def _briefing_time(self, event: Input.Submitted) -> None:
        await self._save({"briefing_time": event.value.strip()})

    @on(Input.Submitted, "#nightly-time")
    @reports_daemon_unavailable
    async def _nightly_time(self, event: Input.Submitted) -> None:
        await self._save({"nightly_time": event.value.strip()})

    @on(Select.Changed, "#weekly-day")
    @reports_daemon_unavailable
    async def _weekly_day(self, event: Select.Changed) -> None:
        if isinstance(event.value, int):
            await self._save({"weekly_day": event.value})

    async def _save(self, change: dict[str, object]) -> None:
        if self._page is None:
            return
        try:
            wanted = ProactiveSettings.model_validate({**self._page.settings.model_dump(), **change})
        except ValueError:
            self.notify(t("Write the time as HH:MM, like 08:00."), severity="error")
            return
        await self._show(await self._proactive.save_settings(wanted))

    @on(Button.Pressed, "#brief")
    @reports_daemon_unavailable
    async def _brief(self) -> None:
        await self._show(await self._proactive.run("briefing"))

    @on(Button.Pressed, "#done")
    @reports_daemon_unavailable
    async def _done(self) -> None:
        await self._show(await self._proactive.close_loop(self._selected.removeprefix(_LOOP), "done"))

    @on(Button.Pressed, "#dismiss")
    @reports_daemon_unavailable
    async def _dismiss(self) -> None:
        await self._show(await self._proactive.close_loop(self._selected.removeprefix(_LOOP), "dismissed"))

    @on(Button.Pressed, "#stop")
    @reports_daemon_unavailable
    async def _stop(self) -> None:
        loop_id = self._selected.removeprefix(_LOOP)
        await self._show(await self._proactive.close_loop(loop_id, "dismissed", stop_suggesting=True))

    @on(Button.Pressed, "#unmute")
    @reports_daemon_unavailable
    async def _unmute(self) -> None:
        await self._show(await self._proactive.mute(self._selected.removeprefix(_MUTED), muted=False))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss(None)
