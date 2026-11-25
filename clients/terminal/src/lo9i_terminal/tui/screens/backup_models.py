"""The backup models (/backups): tried in order when the main model fails on the provider's side (rate limits, quota,
outages), never for what the request asked (core/llm/backups.py). Adding one asks it to answer once; one on the main
model's provider takes its values (its key) where its fields are left empty."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Markdown, Select

from lo9i.client.daemon_client import ModelApi
from lo9i.core.agent import BackupModelStatus, ModelProvider, ModelSettingsError
from lo9i_terminal.i18n import t
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable
from lo9i_terminal.tui.screens.model import field_input, field_value
from lo9i_terminal.tui.section import SettingsSection


class BackupModelsSection(SettingsSection):
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"settings"})

    def __init__(self, model: ModelApi) -> None:
        super().__init__()
        self._model = model
        self._providers: dict[str, ModelProvider] = {}
        self._main = ""
        self._backups: list[BackupModelStatus] = []
        self._inputs: dict[str, Input | Select[str]] = {}
        self._message = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="backups"):
            yield Markdown(id="backups-body")
            yield Select[str]([], prompt=t("Backup"), id="backups-picked")
            with Horizontal(id="backups-order"):
                yield Button(t("Try earlier"), id="backups-up")
                yield Button(t("Try later"), id="backups-down")
                yield Button(t("Remove"), variant="error", id="backups-remove")
            yield Markdown("**" + t("Add a backup") + "**")
            yield Select[str]([], prompt=t("Provider"), id="backups-provider")
            yield Vertical(id="backups-fields")
            yield Input(placeholder=t("Model"), id="backups-model")
            with Horizontal(id="backups-buttons"):
                yield Button(t("Add and test"), variant="success", id="backups-add")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        providers = await self._model.providers()
        self._providers = {p.id: p for p in providers}
        self._main = (await self._model.status()).provider
        select = self.query_one("#backups-provider", Select)
        select.set_options([(p.name, p.id) for p in providers])
        select.value = self._main
        await self._show_provider(self._main)
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a settings change."""
        self._main = (await self._model.status()).provider
        await self._show(await self._model.backups())

    @on(Select.Changed, "#backups-provider")
    async def _provider_changed(self, event: Select.Changed) -> None:
        if isinstance(event.value, str):
            await self._show_provider(event.value)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.close()

    @on(Button.Pressed, "#backups-add")
    @reports_daemon_unavailable
    async def _add(self) -> None:
        self._message = t("Testing the backup…")
        await self._show(self._backups)
        values = {key: field_value(field) for key, field in self._inputs.items()}
        model = self.query_one("#backups-model", Input)
        try:
            listed = await self._model.add_backup(self._provider(), values, model.value.strip())
            self._message = t("Added ✓ It answered.")
            model.value = ""
            await self._show_provider(self._provider())
        except ModelSettingsError as e:
            listed, self._message = self._backups, f"**{e}**"
        await self._show(listed)

    @on(Button.Pressed, "#backups-up")
    async def _up(self) -> None:
        await self._move(-1)

    @on(Button.Pressed, "#backups-down")
    async def _down(self) -> None:
        await self._move(1)

    @reports_daemon_unavailable
    async def _move(self, by: int) -> None:
        ids = [b.id for b in self._backups]
        picked = self._picked()
        if picked not in ids or not 0 <= ids.index(picked) + by < len(ids):
            return
        at = ids.index(picked)
        ids[at], ids[at + by] = ids[at + by], ids[at]
        await self._show(await self._model.order_backups(ids))

    @on(Button.Pressed, "#backups-remove")
    @reports_daemon_unavailable
    async def _remove(self) -> None:
        if picked := self._picked():
            await self._show(await self._model.remove_backup(picked))

    async def _show_provider(self, provider_id: str) -> None:
        provider = self._providers.get(provider_id)
        if provider is None:
            return
        box = self.query_one("#backups-fields", Vertical)
        await box.remove_children()
        self._inputs = {f.key: field_input(f, None) for f in provider.fields}
        await box.mount_all(list(self._inputs.values()))

    async def _show(self, backups: list[BackupModelStatus]) -> None:
        picked = self._picked()
        self._backups = backups
        select = self.query_one("#backups-picked", Select)
        select.set_options([(f"{i}. {b.model}", b.id) for i, b in enumerate(backups, 1)])
        if picked in {b.id for b in backups}:
            select.value = picked
        lines = ["## " + t("Backup models"), t("Tried in order when the main model's provider fails.")]
        lines += [self._line(i, b) for i, b in enumerate(backups, 1)] or [t("No backup models yet.")]
        if self._provider() == self._main:
            lines.append(t("Fields left empty use the main model's."))
        if self._message:
            lines.append(self._message)
        await self.query_one("#backups-body", Markdown).update("\n\n".join(lines))

    def _line(self, number: int, backup: BackupModelStatus) -> str:
        provider = self._providers.get(backup.provider)
        name = provider.name if provider else backup.provider
        key = " · " + t("main model's key") if backup.uses_main_values and not backup.secrets_set else ""
        return f"{number}. `{backup.model}` ({name}{key})"

    def _picked(self) -> str:
        value = self.query_one("#backups-picked", Select).value
        return value if isinstance(value, str) else ""

    def _provider(self) -> str:
        value = self.query_one("#backups-provider", Select).value
        return value if isinstance(value, str) else ""
