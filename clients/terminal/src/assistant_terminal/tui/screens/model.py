"""The model the assistant uses: the provider, the values it asks for (keys, URLs, regions) and the
models. Set here, it overrides .env and applies at once. Saving installs the provider's package the
first time, then asks each model to answer once, so a wrong key or model id shows right away. Secret
values are typed here and go straight to the daemon; they're never shown again."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, Select

from assistant.client.daemon_client import ModelApi
from assistant.core.agent import ModelProvider, ModelSettingsError, ModelStatus, ProviderField
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class ModelScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, model: ModelApi) -> None:
        super().__init__()
        self._model = model
        self._providers: dict[str, ModelProvider] = {}
        self._status: ModelStatus | None = None
        self._message = ""
        # The shown provider's field inputs, by field key.
        self._inputs: dict[str, Input] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="model"):
            yield Markdown(id="model-body")
            yield Select[str]([], prompt="Provider", id="model-provider")
            yield Markdown(id="model-help")
            yield Vertical(id="model-fields")
            yield Input(placeholder="Main model", id="model-main")
            yield Input(placeholder="Worker model (summaries, titles)", id="model-worker")
            with Horizontal(id="model-buttons"):
                yield Button("Save and test", variant="success", id="save")
                yield Button("Use .env instead", id="reset")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        providers = await self._model.providers()
        self._providers = {p.id: p for p in providers}
        self._status = await self._model.status()
        select = self.query_one("#model-provider", Select)
        select.set_options([(p.name, p.id) for p in providers])
        select.value = self._status.provider
        await self._show_provider(self._status.provider)

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a settings change."""
        self._status = await self._model.status()
        await self._show()

    @on(Select.Changed, "#model-provider")
    async def _provider_changed(self, event: Select.Changed) -> None:
        if isinstance(event.value, str):
            await self._show_provider(event.value)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#save")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        provider = self._providers.get(self._provider())
        installing = provider is not None and not provider.installed
        self._message = (
            f"Installing {provider.package}, then testing the models…"
            if installing and provider
            else "Testing the models…"
        )
        await self._show()
        values = {key: field.value.strip() for key, field in self._inputs.items()}
        main, worker = (self.query_one(f"#model-{n}", Input).value.strip() for n in ("main", "worker"))
        try:
            self._status = await self._model.set(self._provider(), values, main, worker)
            self._message = "Saved ✓ Both models answered. The assistant uses them from now on."
            self._providers = {p.id: p for p in await self._model.providers()}
            await self._show_provider(self._status.provider)
        except ModelSettingsError as e:
            self._message = f"**{e}**"
        await self._show()

    @on(Button.Pressed, "#reset")
    @reports_daemon_unavailable
    async def _reset(self) -> None:
        self._status = await self._model.reset()
        self._message = "Using the model from .env again."
        select = self.query_one("#model-provider", Select)
        select.value = self._status.provider
        await self._show_provider(self._status.provider)

    async def _show_provider(self, provider_id: str) -> None:
        """Show a provider's fields: the current values for the one in use, its suggestions otherwise."""
        provider, status = self._providers.get(provider_id), self._status
        if provider is None or status is None:
            return
        current = provider_id == status.provider
        self.query_one("#model-main", Input).value = status.model if current else provider.model
        self.query_one("#model-worker", Input).value = status.worker_model if current else provider.worker_model
        box = self.query_one("#model-fields", Vertical)
        await box.remove_children()
        self._inputs = {f.key: _field_input(f, status if current else None) for f in provider.fields}
        await box.mount_all(list(self._inputs.values()))
        await self.query_one("#model-help", Markdown).update(_help(provider))
        await self._show()

    async def _show(self) -> None:
        status = self._status
        if status is None:
            return
        self.query_one("#reset").display = status.source == "app"
        name = self._providers[status.provider].name if status.provider in self._providers else status.provider
        source = "set here" if status.source == "app" else "from .env"
        lines = [f"## Model: {name} ({source})", f"Main: `{status.model}` · Worker: `{status.worker_model}`"]
        if self._message:
            lines.append(self._message)
        await self.query_one("#model-body", Markdown).update("\n\n".join(lines))

    def _provider(self) -> str:
        value = self.query_one("#model-provider", Select).value
        return value if isinstance(value, str) else ""


def _field_input(field: ProviderField, status: ModelStatus | None) -> Input:
    """An input for a provider's field, with the current value when it isn't secret."""
    saved = status is not None and field.key in status.secrets_set
    hint = " (saved; leave empty to keep it)" if saved else "" if field.required else " (optional)"
    value = status.values.get(field.key, "") if status is not None and not field.secret else ""
    return Input(value, placeholder=f"{field.label}{hint}", password=field.secret)


def _help(provider: ModelProvider) -> str:
    lines = [f"**{f.label}**: {f.help}" for f in provider.fields if f.help]
    if provider.help:
        lines.insert(0, provider.help)
    if not provider.installed:
        lines.append(f"Saving installs `{provider.package}` first, which can take a few minutes.")
    return "\n\n".join(lines)
