"""MCP servers: pick one to see its state and tools, choose the tools the assistant gets, trust it,
turn it off, replace its secrets, update it from the extras, or remove it; add one by hand or
install one from the assistant's extras. Refreshes when a server connects or changes."""

from collections.abc import Awaitable, Callable
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, SelectionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import McpApi
from assistant.core.agent import McpServerChanges, McpServerError, McpServerStatus
from assistant_terminal.mcp_text import describe, selection, summary, tool_label
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen
from assistant_terminal.tui.screens.mcp_add import McpAddScreen
from assistant_terminal.tui.screens.mcp_secrets import McpSecretsScreen


class McpScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, mcp: McpApi) -> None:
        super().__init__()
        self._mcp = mcp
        self._shown: dict[str, McpServerStatus] = {}
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="mcp"):
            yield Static("MCP servers", id="mcp-title")
            yield Static("No MCP servers. Add one to give the assistant its tools.", id="mcp-empty")
            with Horizontal(id="mcp-main"):
                yield OptionList(id="mcp-list")
                yield Static(classes="divider")
                with VerticalScroll(id="mcp-detail"):
                    yield Markdown(id="mcp-body")
                    yield SelectionList[str](id="mcp-tools")
            with Horizontal(id="mcp-buttons"):
                yield Button("Add", variant="success", id="add")
                yield Button("Save tools", id="save-tools")
                yield Button("Trust", id="trust")
                yield Button("Turn off", id="toggle")
                yield Button("Secrets", id="secrets")
                yield Button("Update", id="update")
                yield Button("Remove", variant="error", id="remove")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a server connects, fails or changes."""
        servers = await self._mcp.servers()
        self._shown = {s.name: s for s in servers}
        options = self.query_one("#mcp-list", OptionList)
        options.clear_options()
        options.add_options([Option(summary(s), id=s.name) for s in servers])
        self.query_one("#mcp").set_class(not servers, "empty")
        for button in ("#save-tools", "#trust", "#toggle", "#secrets", "#update", "#remove"):
            self.query_one(button).display = bool(servers)
        if not servers:
            self._selected = None
            return
        keep = self._selected if self._selected in self._shown else servers[0].name
        options.highlighted = list(self._shown).index(keep)
        await self._show(keep)

    @reports_daemon_unavailable
    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is not None and event.option.id != self._selected:
            await self._show(event.option.id)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#add")
    @work
    @reports_daemon_unavailable
    async def _add(self) -> None:
        if await self.app.push_screen_wait(McpAddScreen(self._mcp)):
            await self.reload()

    @on(Button.Pressed, "#update")
    @reports_daemon_unavailable
    async def _update(self) -> None:
        server = self._current()
        if server is not None:
            await self._run(lambda: self._mcp.update_from_repository(server.name), f"Updated {server.name}.")

    @on(Button.Pressed, "#save-tools")
    @reports_daemon_unavailable
    async def _save_tools(self) -> None:
        server = self._current()
        if server is not None:
            selected = set(self.query_one("#mcp-tools", SelectionList).selected)
            include, exclude = selection(server.tools, selected)
            await self._change(server.name, McpServerChanges(include=include, exclude=exclude), "Saved the tools.")

    @on(Button.Pressed, "#trust")
    @reports_daemon_unavailable
    async def _trust(self) -> None:
        server = self._current()
        if server is not None:
            await self._change(server.name, McpServerChanges(trusted=not server.trusted))

    @on(Button.Pressed, "#toggle")
    @reports_daemon_unavailable
    async def _toggle(self) -> None:
        server = self._current()
        if server is not None:
            await self._change(server.name, McpServerChanges(enabled=not server.enabled))

    @on(Button.Pressed, "#secrets")
    @work
    @reports_daemon_unavailable
    async def _secrets(self) -> None:
        server = self._current()
        if server is not None and await self.app.push_screen_wait(McpSecretsScreen(self._mcp, server)):
            await self.reload()

    @on(Button.Pressed, "#remove")
    @work
    @reports_daemon_unavailable
    async def _remove(self) -> None:
        server = self._current()
        if server is None or not await self.app.push_screen_wait(ConfirmScreen(f"Remove {server.name}?", "Remove")):
            return
        await self._run(lambda: self._mcp.remove(server.name), f"Removed {server.name}.")

    async def _change(self, name: str, changes: McpServerChanges, done: str = "") -> None:
        await self._run(lambda: self._mcp.change(name, changes), done)

    async def _run(self, action: Callable[[], Awaitable[object]], done: str) -> None:
        try:
            await action()
        except McpServerError as e:
            self.notify(str(e), severity="error")
        else:
            if done:
                self.notify(done)
        await self.reload()

    def _current(self) -> McpServerStatus | None:
        return self._shown.get(self._selected or "")

    async def _show(self, name: str) -> None:
        self._selected = name
        server = self._shown[name]
        self.query_one("#trust", Button).label = "Don't trust" if server.trusted else "Trust"
        self.query_one("#toggle", Button).label = "Turn off" if server.enabled else "Turn on"
        tools = self.query_one("#mcp-tools", SelectionList)
        tools.clear_options()
        tools.add_options([(tool_label(t), t.name, t.selected) for t in server.tools])
        tools.display = self.query_one("#save-tools").display = bool(server.tools)
        self.query_one("#update").display = bool(server.source)
        await self.query_one("#mcp-body", Markdown).update(describe(server))
