"""An installed plugin's settings, from /plugins: the values its fields were given, changed without installing it
again; as the web app's Settings in a plugin's details. A secret's value never comes here: it shows as saved, kept
when left empty, and an optional one can be cleared. Its check runs before anything is saved; what it says shows
here. Returns True when they were saved."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Markdown, Static

from assistant.client.daemon_client import McpApi
from assistant.core.agent import McpServerError, PluginFieldValue, PluginSettings
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class PluginSettingsScreen(ModalScreen[bool]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss(False)", translatable("Close"))]

    def __init__(self, mcp: McpApi, plugin: str) -> None:
        super().__init__()
        self._mcp, self._plugin = mcp, plugin
        self._settings: PluginSettings | None = None
        # Each field's input, and the boxes that remove a saved optional secret, by field key.
        self._inputs: dict[str, Input] = {}
        self._clears: dict[str, Checkbox] = {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="plugin-settings"):
            yield Markdown(
                f"## {t('{name} settings', name=self._plugin)}\n\n"
                + t("What it was given when it was installed. It starts again with what you save."),
                id="plugin-settings-intro",
            )
            yield Vertical(id="plugin-settings-fields")
            yield Markdown(id="plugin-settings-message")
            with Horizontal(id="plugin-settings-buttons"):
                yield Button(t("Save"), variant="success", id="save")
                yield Button(t("Cancel"), id="cancel")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self.query_one("#save").display = False
        try:
            self._settings = await self._mcp.plugin_settings(self._plugin)
        except McpServerError as e:
            await self._say(f"**{e}**")
            return
        if self._settings.check:
            await self._say(t("It checks what you enter before it's saved, and says here if something doesn't work."))
        self._inputs = {f.key: _input(f) for f in self._settings.fields}
        self._clears = {f.key: _clear(f) for f in self._settings.fields if f.secret and f.optional and f.set}
        widgets = [(_label(f), self._inputs[f.key], *self._clear_box(f.key)) for f in self._settings.fields]
        await self.query_one("#plugin-settings-fields", Vertical).mount_all([w for row in widgets for w in row])
        self.query_one("#save").display = True

    def _clear_box(self, key: str) -> list[Checkbox]:
        return [self._clears[key]] if key in self._clears else []

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#save")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        if self._settings is None:
            return
        values, clear = self._change(self._settings)
        if not values and not clear:
            self.dismiss(False)
            return
        if self._settings.check:
            await self._say(t("Checking…"))
        try:
            await self._mcp.change_plugin_settings(self._plugin, values, clear)
        except McpServerError as e:
            await self._say(f"**{e}**")
            return
        self.dismiss(True)

    def _change(self, settings: PluginSettings) -> tuple[dict[str, str], list[str]]:
        """The fields not secret whose value changed, the secret ones typed, and the secret ones to remove."""
        typed = {f.key: self._inputs[f.key].value.strip() for f in settings.fields}
        values = {
            f.key: typed[f.key] for f in settings.fields if (typed[f.key] if f.secret else typed[f.key] != f.value)
        }
        clear = [key for key, box in self._clears.items() if box.value and key not in values]
        return values, clear

    async def _say(self, text: str) -> None:
        await self.query_one("#plugin-settings-message", Markdown).update(text)


def _label(f: PluginFieldValue) -> Static:
    hints = [*([f.help] if f.help else []), *([t("optional")] if f.optional else [])]
    return Static(f.label + (f" ({'; '.join(hints)})" if hints else ""), classes="plugin-settings-label")


def _input(f: PluginFieldValue) -> Input:
    """A field not secret starts with its value; a secret one empty, which keeps it."""
    if not f.secret:
        return Input(value=f.value, id=f"plugin-field-{f.key}")
    placeholder = t("Saved: leave empty to keep it") if f.set else t("Not set")
    return Input(placeholder=placeholder, password=True, id=f"plugin-field-{f.key}")


def _clear(f: PluginFieldValue) -> Checkbox:
    return Checkbox(t("Remove the saved {label}", label=f.label), id=f"plugin-clear-{f.key}")
