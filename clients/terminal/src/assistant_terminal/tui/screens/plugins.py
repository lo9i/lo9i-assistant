"""Plugins: the MCP servers and skills the repositories offer (the official extras and the ones the user
added under Repositories), each installed or not, to install, update or remove; as in the web app's
Plugins page. The list shows at once as the repositories offered it when last checked, then they're checked
again in the background (Refresh checks again); a check that finds something new saves it, announced as
`plugins`, and the list is read again then."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import ClassVar

import httpx
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client import DaemonUnavailableError
from assistant.client.daemon_client import ChannelsApi, EmailApi, McpApi, OAuthApi, RepositoriesApi, SkillsApi
from assistant.core.agent import McpServerError, RepositoryError, RepositoryPlugins, ServerValues, SkillError
from assistant_terminal.i18n import t
from assistant_terminal.plugins_text import (
    Plugin,
    by_category,
    category_label,
    checked_line,
    describe,
    from_repositories,
    has_newer,
    label,
    last_checked,
    matches,
    updatable,
)
from assistant_terminal.tui.channel_setup import ChannelSetup
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen, ConfirmWithOptionScreen
from assistant_terminal.tui.screens.email import EmailScreen
from assistant_terminal.tui.screens.kept_keys import ask_about_keys
from assistant_terminal.tui.screens.plugin_settings import PluginSettingsScreen
from assistant_terminal.tui.screens.plugin_sign_in import PluginSignInScreen
from assistant_terminal.tui.screens.plugin_updates import PluginUpdatesScreen
from assistant_terminal.tui.screens.repositories import RepositoriesScreen
from assistant_terminal.tui.screens.repository_install import RepositoryInstallScreen

_CATEGORY = "category:"


class PluginsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", t("Close"))]
    # The daemon events that change what it shows (AssistantApp.reload_screen): a check that found something new
    # or kept keys (`plugins`), MCP servers installed or removed (`mcp`), skills installed or removed (`skills`), a
    # channel's setup (`channels`), the repositories listed (`settings`).
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"plugins", "mcp", "channels", "settings", "skills"})

    def __init__(
        self,
        repositories: RepositoriesApi,
        mcp: McpApi,
        skills: SkillsApi,
        channels: ChannelsApi,
        email: EmailApi,
        oauth: OAuthApi,
    ) -> None:
        super().__init__()
        self._repositories, self._mcp, self._skills, self._channels = repositories, mcp, skills, channels
        self._email, self._oauth = email, oauth
        self._all: list[Plugin] = []
        # A plugin's key, or "category:<name>" for a category's shared settings.
        self._selected: str | None = None
        # When the repositories were last checked, as the list shown; "" while one never was.
        self._checked = ""
        # The repositories' errors told, so each is told once while it lasts.
        self._told: set[str] = set()
        # Installed plugins with fields of their own, as installed: the ones Settings opens for.
        self._with_settings: set[str] = set()

    def compose(self) -> ComposeResult:
        with Vertical(id="plugins"):
            yield Static(
                t("Plugins: MCP servers, chat channels and skills from the official extras and your repositories"),
                id="plugins-title",
            )
            yield Static("", id="plugins-checked")
            yield Input(placeholder=t("Search plugins"), id="plugins-search")
            with Horizontal(id="plugins-main"):
                yield OptionList(id="plugins-list")
                yield Static(classes="divider")
                with VerticalScroll(id="plugins-detail"):
                    yield Markdown(t("Looking at the extras…"), id="plugin-body")
                    yield Vertical(id="plugin-setup")
            with Horizontal(id="plugins-buttons"):
                yield Button(t("Updates"), variant="primary", id="updates")
                yield Button(t("Install"), variant="success", id="install")
                yield Button(t("Settings"), id="plugin-settings")
                yield Button(t("Update"), id="update")
                yield Button(t("Remove"), variant="error", id="remove")
                yield Button(t("Accounts"), id="email-accounts")
                yield Button(t("Sign in"), id="plugin-sign-in")
                yield Button(t("Repositories"), id="repositories")
                yield Button(t("Refresh"), id="refresh")
                yield Button(t("Daily update checks"), id="checks")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self._show_checks(await self._repositories.update_checks())
        await self._load()
        self._check()

    @on(Button.Pressed, "#checks")
    @reports_daemon_unavailable
    async def _toggle_checks(self) -> None:
        """Off: the extras are checked only when Plugins opens, and no update notifications."""
        enabled = await self._repositories.set_update_checks(not await self._repositories.update_checks())
        self._show_checks(enabled)
        self.notify(t("Daily plugin update checks on.") if enabled else t("Daily plugin update checks off."))

    def _show_checks(self, enabled: bool) -> None:
        self.query_one("#checks", Button).label = (
            t("Daily update checks: on") if enabled else t("Daily update checks: off")
        )

    @reports_daemon_unavailable
    async def _load(self) -> None:
        """As the repositories offered it when last checked; installed or not is read fresh."""
        self._with_settings = {s.name for s in await self._mcp.servers() if s.settings}
        await self._apply(await self._repositories.plugins(cached=True))

    @work(exclusive=True, group="check")
    async def _check(self) -> None:
        """Reaches the repositories again. Quiet when it fails: the list from the last check stays."""
        self._show_checked(checking=True)
        try:
            read = await self._repositories.plugins()
        except (DaemonUnavailableError, httpx.HTTPError):
            self._show_checked(failed=True)
            return
        await self._apply(read)

    async def _apply(self, read: list[RepositoryPlugins]) -> None:
        self._all, unread = from_repositories(read)
        for error in unread:
            if error not in self._told:
                self.notify(error, severity="error", timeout=10)
        self._told = set(unread)
        self._checked = last_checked(read)
        self._show_checked()
        await self._list()

    def _show_checked(self, checking: bool = False, failed: bool = False) -> None:
        line = checked_line(self._checked, checking, failed, datetime.now(UTC))
        self.query_one("#plugins-checked", Static).update(line)

    @on(Button.Pressed, "#repositories")
    @work
    async def _manage_repositories(self) -> None:
        await self.app.push_screen_wait(RepositoriesScreen(self._repositories))
        await self._load()

    async def _list(self) -> None:
        newer = [p for p in self._all if has_newer(p)]
        updates = self.query_one("#updates", Button)
        updates.display, updates.label = bool(newer), t("Updates ({count})", count=len(newer))
        query = self.query_one("#plugins-search", Input).value
        shown = [p for p in self._all if matches(p, query)]
        options = self.query_one("#plugins-list", OptionList)
        options.clear_options()
        options.add_options(_grouped(shown))
        if not shown:
            self._selected = None
            await self._show(None)
            return
        keep = next((p for p in shown if p.key == self._selected), by_category(shown)[0][1][0])
        options.highlighted = options.get_option_index(keep.key)
        await self._show(keep)

    @on(Input.Changed, "#plugins-search")
    async def _search(self) -> None:
        await self._list()

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        key = event.option.id or ""
        await self._show(next((p for p in self._all if p.key == key), None))

    @on(Button.Pressed, "#email-accounts")
    def _email_accounts(self) -> None:
        """An email plugin's accounts."""
        plugin = self._current()
        if plugin is not None:
            self.app.push_screen(EmailScreen(self._email, self._oauth, self._channels, plugin.name))

    @on(Button.Pressed, "#plugin-settings")
    @work
    async def _plugin_settings(self) -> None:
        """An installed plugin's fields, to change what it was given."""
        plugin = self._current()
        if plugin is not None and await self.app.push_screen_wait(PluginSettingsScreen(self._mcp, plugin.name)):
            self.notify(t("Saved {name}'s settings.", name=plugin.name))

    @on(Button.Pressed, "#plugin-sign-in")
    def _plugin_sign_in(self) -> None:
        """A plugin's sign-in with the user's own OAuth app."""
        plugin = self._current()
        if plugin is not None and plugin.server is not None and plugin.server.oauth:
            self.app.push_screen(PluginSignInScreen(self._mcp, self._oauth, plugin.name, plugin.server.oauth))

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#refresh")
    def _refresh(self) -> None:
        self._check()

    @on(Button.Pressed, "#install")
    @work
    @reports_daemon_unavailable
    async def _install(self) -> None:
        plugin = self._current()
        if plugin is None:
            return
        if plugin.server is not None and plugin.server.fields:
            # It asks for values: a screen for just this plugin's fields.
            screen = RepositoryInstallScreen(self._repositories, only=plugin.name, url=plugin.repository.url)
            if await self.app.push_screen_wait(screen):
                self.notify(t("Installed {name}.", name=plugin.name))
            await self._load()
            return
        skills, servers = ([], [ServerValues(plugin.name)]) if plugin.server else ([plugin.name], [])
        url = plugin.repository.url
        await self._run(
            lambda: self._repositories.install(skills, servers, url), t("Installed {name}.", name=plugin.name)
        )

    @on(Button.Pressed, "#update")
    @reports_daemon_unavailable
    async def _update(self) -> None:
        plugin = self._current()
        if plugin is not None:
            update = self._mcp.update_from_repository if plugin.server else self._skills.update_installed
            await self._run(lambda: update(plugin.name), t("Updated {name}.", name=plugin.name))

    @on(Button.Pressed, "#updates")
    @work
    @reports_daemon_unavailable
    async def _updates(self) -> None:
        picked = await self.app.push_screen_wait(PluginUpdatesScreen([p for p in self._all if has_newer(p)]))
        if picked:
            await self._update_many(picked)

    async def _update_many(self, picked: list[Plugin]) -> None:
        """One after the other: an update restarts the plugin. One that fails doesn't stop the rest."""
        updated = []
        for plugin in picked:
            update = self._mcp.update_from_repository if plugin.server else self._skills.update_installed
            try:
                await update(plugin.name)
                updated.append(plugin.name)
            except (RepositoryError, McpServerError, SkillError) as e:
                self.notify(f"{plugin.name}: {e}", severity="error")
        if updated:
            self.notify(t("Updated {name}.", name=", ".join(updated)))
        await self._load()

    @on(Button.Pressed, "#remove")
    @work
    @reports_daemon_unavailable
    async def _remove(self) -> None:
        plugin = self._current()
        if plugin is None:
            return
        if plugin.server is None:
            if await self.app.push_screen_wait(ConfirmScreen(t("Remove {name}?", name=plugin.name), t("Remove"))):
                kept = await self._run(lambda: self._skills.delete(plugin.name), t("Removed {name}.", name=plugin.name))
                await ask_about_keys(self, self._repositories, kept)
            return
        question = t(
            "Remove {name}? Its data stays, for installing it again, unless you delete it too.", name=plugin.name
        )
        option = t("Also delete its data (can't be undone)")
        delete_data = await self.app.push_screen_wait(ConfirmWithOptionScreen(question, t("Remove"), option))
        if delete_data is not None:
            kept = await self._run(
                lambda: self._mcp.remove(plugin.name, delete_data), t("Removed {name}.", name=plugin.name)
            )
            await ask_about_keys(self, self._repositories, kept)

    async def _run[T](self, action: Callable[[], Awaitable[T]], done: str) -> T | None:
        """The action's result; None when it failed, which is told."""
        try:
            result = await action()
            self.notify(done)
        except (RepositoryError, McpServerError, SkillError) as e:
            self.notify(str(e), severity="error")
            result = None
        await self._load()
        return result

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a change in `RELOADS_ON`: a check that found something new, a channel's
        new pairing code. The list is read as last checked, which downloads only a repository never read, and the
        shown plugin's setup."""
        await self._load()
        await self._show_setup(self._current())

    async def _show_setup(self, plugin: Plugin | None) -> None:
        """An installed chat channel's setup, under its details."""
        box = self.query_one("#plugin-setup", Vertical)
        await box.remove_children()
        if plugin is None or plugin.server is None or not plugin.server.channel or not plugin.installed:
            return
        channel = next((c for c in await self._channels.list() if c.name == plugin.name), None)
        if channel is not None:
            await box.mount(ChannelSetup(self._channels, channel))

    def _current(self) -> Plugin | None:
        return next((p for p in self._all if p.key == self._selected), None)

    async def _show(self, plugin: Plugin | None) -> None:
        self._selected = plugin.key if plugin else None
        installed = plugin is not None and plugin.installed
        self.query_one("#install").display = plugin is not None and not installed
        self.query_one("#remove").display = installed
        self.query_one("#update").display = plugin is not None and updatable(plugin)
        email = installed and plugin is not None and plugin.server is not None and plugin.server.email
        self.query_one("#email-accounts").display = email
        self.query_one("#plugin-settings").display = (
            installed and plugin is not None and plugin.name in self._with_settings
        )
        signs_in = installed and plugin is not None and plugin.server is not None and bool(plugin.server.oauth)
        self.query_one("#plugin-sign-in").display = signs_in
        await self._show_setup(plugin)
        if plugin is not None:
            await self.query_one("#plugin-body", Markdown).update(describe(plugin))
        elif self._all:
            await self.query_one("#plugin-body", Markdown).update(t("No matches."))
        else:
            await self.query_one("#plugin-body", Markdown).update(t("The repositories offer no plugins yet."))


def _grouped(shown: list[Plugin]) -> list[Option]:
    """Each category's name, then its plugins."""
    options: list[Option] = []
    for category, group in by_category(shown):
        options.append(Option(f"[b]{category_label(category)}[/b]", id=f"{_CATEGORY}{category}", disabled=True))
        options += [Option(f"  {label(p)}", id=p.key) for p in group]
    return options
