"""Set the Brave Search API key, so web search doesn't depend on public engines and free services
that block or limit automated searches."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown

from assistant.client.daemon_client import WebSearchApi
from assistant.core.agent import InvalidSearchKeyError, WebSearchStatus
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.web_search_text import describe


class WebSearchScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", translatable("Close"))]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"settings"})

    def __init__(self, web_search: WebSearchApi) -> None:
        super().__init__()
        self._web_search = web_search
        self._error = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="web-search"):
            yield Markdown(id="web-search-body")
            yield Input(placeholder=t("Brave Search API key"), password=True, id="web-search-key")
            with Horizontal(id="web-search-buttons"):
                yield Button(t("Save"), variant="success", id="save")
                yield Button(t("Remove key"), variant="error", id="remove")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._show(await self._web_search.status())

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a change (the key set from another client)."""
        await self._show(await self._web_search.status())

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @reports_daemon_unavailable
    async def on_input_submitted(self, _: Input.Submitted) -> None:
        await self._save()

    @on(Button.Pressed, "#save")
    @reports_daemon_unavailable
    async def _save(self) -> None:
        key_input = self.query_one("#web-search-key", Input)
        if not key_input.value.strip():
            return
        try:
            status = await self._web_search.set_brave_key(key_input.value.strip())
            key_input.value, self._error = "", ""
        except InvalidSearchKeyError as e:
            status, self._error = await self._web_search.status(), str(e)
        await self._show(status)

    @on(Button.Pressed, "#remove")
    @reports_daemon_unavailable
    async def _remove(self) -> None:
        self._error = ""
        await self._show(await self._web_search.remove_brave_key())

    async def _show(self, status: WebSearchStatus) -> None:
        # Controls first, text last: once the text shows the new state, the controls match it.
        self.query_one("#web-search-key").display = not status.brave_key_set
        self.query_one("#save").display = not status.brave_key_set
        self.query_one("#remove").display = status.brave_key_set
        await self.query_one("#web-search-body", Markdown).update(describe(status, self._error))
