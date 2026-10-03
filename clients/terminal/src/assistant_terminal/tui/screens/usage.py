"""Tokens, and tool and skill calls, over the last 7 or 30 days."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown

from assistant.client.daemon_client import UsageApi
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.usage_text import describe


class UsageScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, usage: UsageApi) -> None:
        super().__init__()
        self._usage = usage

    def compose(self) -> ComposeResult:
        with Vertical(id="usage"):
            with VerticalScroll(id="usage-scroll"):
                yield Markdown(id="usage-body")
            with Horizontal(id="usage-buttons"):
                yield Button("7 days", id="days-7")
                yield Button("30 days", id="days-30")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._load(7)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#days-7")
    @reports_daemon_unavailable
    async def _last_week(self) -> None:
        await self._load(7)

    @on(Button.Pressed, "#days-30")
    @reports_daemon_unavailable
    async def _last_month(self) -> None:
        await self._load(30)

    async def _load(self, days: int) -> None:
        report, tokens = await self._usage.report(days), await self._usage.tokens(days)
        await self.query_one("#usage-body", Markdown).update(describe(report, tokens))
