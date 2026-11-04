"""The spending limits (/limits): what model calls may spend per run of a scheduled job, per job a day, per
conversation and overall a day, in US dollars, each empty for none (core/usage/limits.py)."""

from dataclasses import replace

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Markdown

from lo9i.client.daemon_client import UsageApi
from lo9i.core.agent import SpendingStatus
from lo9i.core.usage.limits import SpendingLimits, SpendingLimitsError
from lo9i_terminal.i18n import t
from lo9i_terminal.limits_text import LIMITS, NotAnAmountError, amount_of, describe
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable
from lo9i_terminal.tui.section import SettingsSection


class SpendingLimitsSection(SettingsSection):
    def __init__(self, usage: UsageApi) -> None:
        super().__init__()
        self._usage = usage

    def compose(self) -> ComposeResult:
        with Vertical(id="spending"):
            yield Markdown(id="spending-body")
            for kind, (_, label) in LIMITS.items():
                with Horizontal(classes="spending-limit"):
                    yield Label(t(label))
                    yield Input(placeholder=t("No limit"), id=f"limit-{kind}")
            with Horizontal(id="spending-buttons"):
                yield Button(t("Save"), variant="success", id="save")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._show(await self._usage.spending())

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.close()

    @reports_daemon_unavailable
    async def on_input_submitted(self, _: Input.Submitted) -> None:
        await self._save()

    @on(Button.Pressed, "#save")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        try:
            status = await self._usage.set_limits(self._typed())
        except (NotAnAmountError, SpendingLimitsError) as e:
            self.notify(str(e), severity="error")
            return
        await self._show(status)
        self.notify(t("Spending limits saved."))

    def _typed(self) -> SpendingLimits:
        typed = {kind: amount_of(self.query_one(f"#limit-{kind}", Input).value) for kind in LIMITS}
        return replace(SpendingLimits(), **typed)

    async def _show(self, status: SpendingStatus) -> None:
        for kind in LIMITS:
            limit = status.limits.of(kind)
            self.query_one(f"#limit-{kind}", Input).value = "" if limit is None else f"{limit:g}"
        await self.query_one("#spending-body", Markdown).update(describe(status))
