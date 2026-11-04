"""The briefing and the reviews, as the web app's Settings → General → Briefing and reviews: each feature on or off,
the briefing's and the nightly review's times, the weekly review's day, and the kinds muted, each with Suggest again. The open
loops are Home's Open loops card (/home); a briefing or review that fails is an alert (/alerts)."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, Static, Switch

from lo9i.client.daemon_client import ProactiveApi
from lo9i.core.agent import ProactivePage, ProactiveSettings
from lo9i_terminal.i18n import t, translatable
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable
from lo9i_terminal.tui.section import SettingsSection

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


class BriefingSection(SettingsSection):
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"proactive"})

    def __init__(self, proactive: ProactiveApi) -> None:
        super().__init__()
        self._proactive = proactive
        self._page: ProactivePage | None = None
        self._muted: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="briefing"):
            yield Static(t("Briefing and reviews"), id="briefing-title")
            with VerticalScroll(id="briefing-detail"):
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
                yield Vertical(id="briefing-muted")
            with Horizontal(id="briefing-buttons"):
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
        self._fill_settings(page.settings)
        await self._fill_muted(page.settings.muted)

    def _fill_settings(self, chosen: ProactiveSettings) -> None:
        for key, _ in _SWITCHES:
            with self.query_one(f"#switch-{key}", Switch).prevent(Switch.Changed):
                self.query_one(f"#switch-{key}", Switch).value = getattr(chosen, key)
        self.query_one("#briefing-time", Input).value = chosen.briefing_time
        self.query_one("#nightly-time", Input).value = chosen.nightly_time
        with self.query_one("#weekly-day", Select).prevent(Select.Changed):
            self.query_one("#weekly-day", Select).value = chosen.weekly_day

    async def _fill_muted(self, muted: list[str]) -> None:
        """The kinds muted with "less of this", each with Suggest again; nothing when none is."""
        self._muted = list(muted)
        box = self.query_one("#briefing-muted", Vertical)
        await box.remove_children()
        if not muted:
            return
        rows: list[Widget] = [Label(t("Not suggested any more"), classes="briefing-muted-title")]
        for n, kind in enumerate(muted):
            rows.append(Horizontal(Label(kind), Button(t("Suggest again"), id=f"unmute-{n}"), classes="briefing-muted-row"))
        await box.mount_all(rows)

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

    @on(Button.Pressed, ".briefing-muted-row Button")
    @reports_daemon_unavailable
    async def _unmute(self, event: Button.Pressed) -> None:
        kind = self._muted[int((event.button.id or "").removeprefix("unmute-"))]
        await self._show(await self._proactive.mute(kind, muted=False))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.close()
