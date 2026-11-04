"""The briefing and the reviews, as the web app's Settings → General → Briefing and reviews: each feature on or off,
the briefing's and the nightly review's times, the weekly review's day, and the kinds muted (Suggest again). The open
loops are Home's Open loops card (/home); a briefing or review that fails is an alert (/alerts)."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Markdown, OptionList, Select, Static, Switch
from textual.widgets.option_list import Option

from assistant.client.daemon_client import ProactiveApi
from assistant.core.agent import ProactivePage, ProactiveSettings
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.page import PageScreen

_SETTINGS = "settings"
_MUTED = "muted:"
_INTRO = translatable(
    "What the assistant does on its own, at the times below, in the assistant computer's time zone. It suggests; it "
    "never acts for you."
)
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
        self._selected = _SETTINGS

    def compose_page(self) -> ComposeResult:
        with Vertical(id="briefing"):
            yield Static(t("Briefing and reviews"), id="briefing-title")
            with Horizontal(id="briefing-main"):
                yield OptionList(id="briefing-list")
                yield Static(classes="divider")
                with VerticalScroll(id="briefing-detail"):
                    yield Markdown(id="briefing-body")
                    with Vertical(id="briefing-settings"):
                        yield Label(t(_INTRO), id="briefing-intro")
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
                yield Button(t("Suggest again"), id="unmute")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a setting or a muted kind is saved."""
        await self._show(await self._proactive.get())

    async def _show(self, page: ProactivePage) -> None:
        self._page = page
        options = [Option(t("Settings"), id=_SETTINGS)]
        options += [Option(t("Muted: {kind}", kind=k), id=_MUTED + k) for k in page.settings.muted]
        ids = [o.id for o in options]
        self._selected = self._selected if self._selected in ids else _SETTINGS
        listed = self.query_one("#briefing-list", OptionList)
        listed.clear_options()
        listed.add_options(options)
        listed.highlighted = ids.index(self._selected)
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
        muted = self._selected.startswith(_MUTED)
        self.query_one("#unmute").display = muted
        self.query_one("#briefing-settings").display = not muted
        body = self.query_one("#briefing-body", Markdown)
        body.display = muted
        if muted:
            await body.update(t("Not suggested any more: {kind}.", kind=self._selected.removeprefix(_MUTED)))

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._selected = event.option.id or _SETTINGS
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

    @on(Button.Pressed, "#unmute")
    @reports_daemon_unavailable
    async def _unmute(self) -> None:
        await self._show(await self._proactive.mute(self._selected.removeprefix(_MUTED), muted=False))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss(None)
