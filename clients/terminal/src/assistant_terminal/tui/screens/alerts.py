"""Alerts, as the web app's Alerts page: MCP servers and skills that keep failing or need the user to sign in again,
and what the health check found new or growing, newest first, each listed by when it last happened with the whole of
the one picked beside the list. Open goes to it (its server, skill or cause picked), Dismiss takes it off until it
happens again, Dismiss all asks first."""

from collections.abc import Callable
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client.alerts import AlertsApi
from assistant.core.agent import Alert
from assistant_terminal.alerts_text import alerted_at, describe
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.page import PageScreen
from assistant_terminal.tui.screens.confirm import ConfirmScreen


def _key(alert: Alert) -> str:
    return f"{alert.area}/{alert.name}"


class AlertsScreen(PageScreen[None]):
    PAGE = "alerts"
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", translatable("Close"))]
    # Failures are kept with the servers and skills, and the health check's with its reports.
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"mcp", "skills", "doctor", "proactive"})

    def __init__(self, alerts: AlertsApi, open_alert: Callable[[Alert], object]) -> None:
        """`open_alert`: has the app show its server, skill or the health check's cause in this page's place, once
        this page's handler is done (closing the page from inside it would wait on itself)."""
        super().__init__()
        self._alerts = alerts
        self._open_alert = open_alert
        self._shown: dict[str, Alert] = {}
        self._selected: str | None = None

    def compose_page(self) -> ComposeResult:
        with Vertical(id="alerts"):
            yield Static(t("Needs attention"), id="alerts-title")
            yield Static(t("Nothing needs attention."), id="alerts-empty")
            with Horizontal(id="alerts-main"):
                yield OptionList(id="alerts-list")
                yield Static(classes="divider")
                with VerticalScroll(id="alerts-detail"):
                    yield Markdown(id="alerts-body")
            with Horizontal(id="alerts-buttons"):
                yield Button(t("Open"), variant="success", id="open")
                yield Button(t("Dismiss"), id="dismiss")
                yield Button(t("Dismiss all"), variant="error", id="dismiss-all")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        found = await self._alerts.list()
        self._shown = {_key(a): a for a in found}
        options = self.query_one("#alerts-list", OptionList)
        options.clear_options()
        options.add_options([Option(alerted_at(a), id=key) for key, a in self._shown.items()])
        self.query_one("#alerts").set_class(not found, "empty")
        for button in ("#open", "#dismiss", "#dismiss-all"):
            self.query_one(button).display = bool(found)
        if not found:
            self._selected = None
            self.query_one("#close", Button).focus()
            return
        keep = self._selected if self._selected in self._shown else _key(found[0])
        options.highlighted = list(self._shown).index(keep)
        await self._show(keep)

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Only for one the list still shows: a highlight can come in after a dismissal built the list again."""
        if event.option.id in self._shown:
            await self._show(event.option.id)

    async def _show(self, key: str) -> None:
        self._selected = key
        await self.query_one("#alerts-body", Markdown).update(describe(self._shown[key]))
        self.query_one("#alerts-detail", VerticalScroll).scroll_home(animate=False)

    @on(Button.Pressed, "#open")
    def _open(self) -> None:
        alert = self._shown.get(self._selected or "")
        if alert is not None:
            self._open_alert(alert)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#dismiss")
    @reports_daemon_unavailable
    async def _dismiss(self) -> None:
        alert = self._shown.get(self._selected or "")
        if alert is not None:
            await self._alerts.dismiss(alert.area, alert.name)
            await self.reload()

    @on(Button.Pressed, "#dismiss-all")
    @work
    @reports_daemon_unavailable
    async def _dismiss_all(self) -> None:
        question = t("Dismiss every alert? They come back if the problem happens again.")
        if not await self.app.push_screen_wait(ConfirmScreen(question, t("Dismiss all"))):
            return
        # One at a time: the health check's alerts share one record, so dismissing them at once loses some.
        for alert in list(self._shown.values()):
            await self._alerts.dismiss(alert.area, alert.name)
        await self.reload()
