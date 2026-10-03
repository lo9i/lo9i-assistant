"""Plugins: the MCP servers and skills the assistant's extras offer, each installed or not, to install,
update or remove; as in the web app's Plugins page. The extras are downloaded to list them, so the
list loads when the screen opens and after each action, not on every daemon event."""

from collections.abc import Awaitable, Callable
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import McpApi, RepositoriesApi, SkillsApi
from assistant.core.agent import McpServerError, RepositoryError, ServerValues, SkillError
from assistant_terminal.plugins_text import Plugin, describe, label, matches, plugins, updatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen
from assistant_terminal.tui.screens.repository_install import RepositoryInstallScreen


class PluginsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, repositories: RepositoriesApi, mcp: McpApi, skills: SkillsApi) -> None:
        super().__init__()
        self._repositories, self._mcp, self._skills = repositories, mcp, skills
        self._all: list[Plugin] = []
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="plugins"):
            yield Static("Plugins: MCP servers and skills from the assistant's extras", id="plugins-title")
            yield Input(placeholder="Search plugins", id="plugins-search")
            with Horizontal(id="plugins-main"):
                yield OptionList(id="plugins-list")
                yield Static(classes="divider")
                with VerticalScroll(id="plugins-detail"):
                    yield Markdown("Looking at the extras…", id="plugin-body")
            with Horizontal(id="plugins-buttons"):
                yield Button("Install", variant="success", id="install")
                yield Button("Update", id="update")
                yield Button("Remove", variant="error", id="remove")
                yield Button("Refresh", id="refresh")
                yield Button("Daily update checks", id="checks")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self._show_checks(await self._repositories.update_checks())
        await self._load()

    @on(Button.Pressed, "#checks")
    @reports_daemon_unavailable
    async def _toggle_checks(self) -> None:
        """Off: the extras are checked only when Plugins opens, and no update notifications."""
        enabled = await self._repositories.set_update_checks(not await self._repositories.update_checks())
        self._show_checks(enabled)
        self.notify(f"Daily plugin update checks {'on' if enabled else 'off'}.")

    def _show_checks(self, enabled: bool) -> None:
        self.query_one("#checks", Button).label = f"Daily update checks: {'on' if enabled else 'off'}"

    @reports_daemon_unavailable
    async def _load(self) -> None:
        try:
            self._all = plugins(await self._repositories.browse())
        except RepositoryError as e:
            self._all = []
            await self.query_one("#plugin-body", Markdown).update(f"**{e}**")
        await self._list()

    async def _list(self) -> None:
        query = self.query_one("#plugins-search", Input).value
        shown = [p for p in self._all if matches(p, query)]
        options = self.query_one("#plugins-list", OptionList)
        options.clear_options()
        options.add_options([Option(label(p), id=p.key) for p in shown])
        if not shown:
            self._selected = None
            await self._show(None)
            return
        keep = next((p for p in shown if p.key == self._selected), shown[0])
        options.highlighted = shown.index(keep)
        await self._show(keep)

    @on(Input.Changed, "#plugins-search")
    async def _search(self) -> None:
        await self._list()

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        await self._show(next((p for p in self._all if p.key == event.option.id), None))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#refresh")
    async def _refresh(self) -> None:
        await self._load()

    @on(Button.Pressed, "#install")
    @work
    @reports_daemon_unavailable
    async def _install(self) -> None:
        plugin = self._current()
        if plugin is None:
            return
        if plugin.server is not None and plugin.server.fields:
            # It asks for values: a screen for just this plugin's fields.
            if await self.app.push_screen_wait(RepositoryInstallScreen(self._repositories, only=plugin.name)):
                self.notify(f"Installed {plugin.name}.")
            await self._load()
            return
        skills, servers = ([], [ServerValues(plugin.name)]) if plugin.server else ([plugin.name], [])
        await self._run(lambda: self._repositories.install(skills, servers), f"Installed {plugin.name}.")

    @on(Button.Pressed, "#update")
    @reports_daemon_unavailable
    async def _update(self) -> None:
        plugin = self._current()
        if plugin is not None:
            update = self._mcp.update_from_repository if plugin.server else self._skills.update_installed
            await self._run(lambda: update(plugin.name), f"Updated {plugin.name}.")

    @on(Button.Pressed, "#remove")
    @work
    @reports_daemon_unavailable
    async def _remove(self) -> None:
        plugin = self._current()
        if plugin is None or not await self.app.push_screen_wait(ConfirmScreen(f"Remove {plugin.name}?", "Remove")):
            return
        remove = self._mcp.remove if plugin.server else self._skills.delete
        await self._run(lambda: remove(plugin.name), f"Removed {plugin.name}.")

    async def _run(self, action: Callable[[], Awaitable[object]], done: str) -> None:
        try:
            await action()
            self.notify(done)
        except (RepositoryError, McpServerError, SkillError) as e:
            self.notify(str(e), severity="error")
        await self._load()

    def _current(self) -> Plugin | None:
        return next((p for p in self._all if p.key == self._selected), None)

    async def _show(self, plugin: Plugin | None) -> None:
        self._selected = plugin.key if plugin else None
        installed = plugin is not None and plugin.installed
        self.query_one("#install").display = plugin is not None and not installed
        self.query_one("#remove").display = installed
        self.query_one("#update").display = plugin is not None and updatable(plugin)
        if plugin is not None:
            await self.query_one("#plugin-body", Markdown).update(describe(plugin))
        elif self._all:
            await self.query_one("#plugin-body", Markdown).update("No matches.")
        else:
            await self.query_one("#plugin-body", Markdown).update("The extras offer no plugins yet.")
