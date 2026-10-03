"""The model the assistant uses: provider, key and models. Set here, it overrides .env and applies at
once. Saving asks each model to answer once, so a wrong key or model id shows right away. The key is
typed here and goes straight to the daemon; it's never shown again."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, Select

from assistant.client.daemon_client import ModelApi
from assistant.core.agent import ModelProvider, ModelSettingsError, ModelStatus
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class ModelScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, model: ModelApi) -> None:
        super().__init__()
        self._model = model
        self._providers: dict[str, ModelProvider] = {}
        self._status: ModelStatus | None = None
        self._message = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="model"):
            yield Markdown(id="model-body")
            yield Select[str]([], prompt="Provider", id="model-provider")
            yield Markdown(id="model-help")
            yield Input(password=True, id="model-key")
            yield Input(placeholder="Server URL (empty for OpenAI itself)", id="model-url")
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
        self._message = "Testing the models…"
        await self._show()
        value = {
            name: self.query_one(f"#model-{name}", Input).value.strip() for name in ("key", "url", "main", "worker")
        }
        try:
            self._status = await self._model.set(
                self._provider(), value["key"], value["url"], value["main"], value["worker"]
            )
            self._message = "Saved ✓ Both models answered. The assistant uses them from now on."
            self.query_one("#model-key", Input).value = ""
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
        """Fill the fields for a provider: the current values for the one in use, its suggestions otherwise."""
        provider, status = self._providers.get(provider_id), self._status
        if provider is None or status is None:
            return
        current = provider_id == status.provider
        self.query_one("#model-main", Input).value = status.model if current else provider.model
        self.query_one("#model-worker", Input).value = status.worker_model if current else provider.worker_model
        self.query_one("#model-url", Input).value = status.base_url if current else ""
        self.query_one("#model-url").display = provider.takes_base_url
        key = self.query_one("#model-key", Input)
        key.value = ""
        saved = current and status.key_set
        key.placeholder = f"{provider.key_label} (saved; leave empty to keep it)" if saved else provider.key_label
        await self.query_one("#model-help", Markdown).update(provider.key_help)
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
