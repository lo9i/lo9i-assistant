"""A plugin whose new version asks for values it wasn't given (its update raised UpdateNeedsValuesError): the new
version's fields the installed one has no value for, from the repositories' listing, and the update again with
them; as the web app's UpdateValuesDialog. Returns True once it updated."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, Static

from lo9i.client.daemon_client import McpApi, RepositoriesApi
from lo9i.core.agent import McpServerError, ServerField
from lo9i_terminal.i18n import t, translatable
from lo9i_terminal.plugins_text import from_repositories, missing_fields
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable


class UpdateValuesScreen(ModalScreen[bool]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(False)", translatable("Close"))]

    def __init__(self, mcp: McpApi, repositories: RepositoriesApi, plugin: str, reason: str) -> None:
        """`reason`: what the update said, shown when those fields can't be told."""
        super().__init__()
        self._mcp, self._repositories = mcp, repositories
        self._plugin, self._reason = plugin, reason
        self._fields: list[ServerField] = []
        self._inputs: dict[str, Input] = {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="update-values"):
            yield Markdown(
                f"## {t('Update {name}', name=self._plugin)}\n\n"
                + t("Its new version asks for something it wasn't given when it was installed.")
            )
            yield Vertical(id="update-values-fields")
            yield Markdown(id="update-values-message")
            with Horizontal(id="update-values-buttons"):
                yield Button(t("Update"), variant="success", id="update")
                yield Button(t("Cancel"), id="cancel")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self.query_one("#update").display = False
        await self._say(t("Loading…"))
        try:
            found, _ = from_repositories(await self._repositories.plugins(cached=True))
            self._fields = missing_fields(found, self._plugin, await self._mcp.plugin_settings(self._plugin))
        except McpServerError as e:
            await self._say(f"**{e}**")
            return
        if not self._fields:
            await self._say(f"**{self._reason}**")
            return
        self._inputs = {f.key: _input(f) for f in self._fields}
        rows = [(_label(f), self._inputs[f.key]) for f in self._fields]
        await self.query_one("#update-values-fields", Vertical).mount_all([w for row in rows for w in row])
        self.query_one("#update").display = True
        await self._say("")
        self._inputs[self._fields[0].key].focus()

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#update")
    @reports_daemon_unavailable
    async def _update(self) -> None:
        values = {key: field_input.value.strip() for key, field_input in self._inputs.items()}
        empty = next((f for f in self._fields if not f.optional and not values[f.key]), None)
        if empty is not None:
            await self._say(f"**{t('{name} needs {field}.', name=self._plugin, field=empty.label)}**")
            return
        await self._say(t("Updating…"))
        try:
            await self._mcp.update_from_repository(self._plugin, values)
        except McpServerError as e:
            await self._say(f"**{e}**")
            return
        self.dismiss(True)

    async def _say(self, text: str) -> None:
        await self.query_one("#update-values-message", Markdown).update(text)


def _label(f: ServerField) -> Static:
    hints = [*([f.help] if f.help else []), *([t("optional")] if f.optional else [])]
    return Static(f.label + (f" ({'; '.join(hints)})" if hints else ""), classes="plugin-settings-label")


def _input(f: ServerField) -> Input:
    return Input(password=f.secret, id=f"update-field-{f.key}")
