import asyncio
from dataclasses import replace

from textual.widgets import Button, Checkbox, Input, Markdown, OptionList

from assistant.core.agent import (
    FoundServer,
    PluginUpdate,
    Repository,
    RepositoryContents,
    RepositoryPlugins,
    ServerField,
)
from assistant.core.repositories.known import EXTRAS
from assistant_terminal.plugins_text import Plugin, by_category, describe, from_repositories
from assistant_terminal.tui.screens import PluginSettingsScreen, PluginsScreen
from assistant_terminal.tui.screens.confirm import ConfirmWithOptionScreen
from assistant_terminal.tui.screens.repository_install import RepositoryInstallScreen, _field_input
from tests.terminal.conftest import _mcp_status, wait_for


async def _open(pilot, app) -> PluginsScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/plugins", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, PluginsScreen))
    return app.screen


def _body(screen) -> str:
    return screen.query_one("#plugin-body", Markdown).source


async def test_lists_the_extras_with_a_search_and_installs_one_that_asks_for_nothing_at_once(app, client):
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        plugins = screen.query_one("#plugins-list", OptionList)
        # The three are in Other, under its name.
        await wait_for(pilot, lambda: plugins.option_count == 4)
        assert "Kind: MCP server" in _body(screen) and screen.query_one("#install").display
        screen.query_one("#plugins-search", Input).value = "page"
        await wait_for(pilot, lambda: plugins.option_count == 2 and "## weather" in _body(screen))
        assert "Version: 1.1.0" in _body(screen)
        screen.query_one("#install", Button).press()
        await wait_for(pilot, lambda: "weather" in client.mcp.items)
        assert client.repositories.installed[-1][2][0].name == "weather"
        await wait_for(pilot, lambda: "State: installed" in _body(screen) and screen.query_one("#update").display)
        assert "Version: 1.0.0 → 1.1.0" in _body(screen)
        screen.query_one("#update", Button).press()
        await wait_for(pilot, lambda: getattr(client.mcp, "updated", None) == "weather")
        screen.query_one("#remove", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmWithOptionScreen))
        app.screen.query_one("#confirm-yes", Button).press()
        await wait_for(pilot, lambda: "weather" not in client.mcp.items)
        assert client.mcp.data_deleted is False  # the box starts unchecked


async def test_a_plugin_that_asks_for_values_gets_a_screen_for_just_those(app, client):
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: "## calendar" in _body(screen))
        assert "Asks for: User, Password" in _body(screen)
        screen.query_one("#install", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, RepositoryInstallScreen))
        install = app.screen
        fields = list(install.query("#repository-fields Input").results(Input))
        await wait_for(pilot, lambda: len(list(install.query("#repository-fields Input"))) == 2)
        fields = list(install.query("#repository-fields Input").results(Input))
        fields[0].value, fields[1].value = "ana", "pw"
        install.query_one("#install", Button).press()
        await wait_for(pilot, lambda: app.screen is screen and "calendar" in client.mcp.items)
        assert client.repositories.installed[-1][0] == EXTRAS


async def test_daily_update_checks_are_turned_on_and_off_here(app, client):
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        checks = screen.query_one("#checks", Button)
        await wait_for(pilot, lambda: str(checks.label) == "Daily update checks: on")
        checks.press()
        await wait_for(
            pilot, lambda: not client.repositories.checks and str(checks.label) == "Daily update checks: off"
        )


async def test_new_plugin_updates_are_told_once_and_point_to_plugins(app, client):
    client.repositories.pending = [PluginUpdate("server", "weather", "1.0.0", "1.1.0")]
    async with app.run_test(size=(120, 44)) as pilot:
        await wait_for(pilot, lambda: _told(app) == 1)
        assert "Plugin update: weather 1.0.0 → 1.1.0. See /plugins." in _messages(app)
        client.bus.put_nowait(("plugins", {}))
        client.repositories.pending.append(PluginUpdate("skill", "expenses", "1.0.0", "2.0.0"))
        client.bus.put_nowait(("plugins", {}))
        await wait_for(pilot, lambda: _told(app) == 2)
        assert "Plugin update: expenses 1.0.0 → 2.0.0. See /plugins." in _messages(app)


def _messages(app) -> list[str]:
    return [str(n.message) for n in app._notifications]


def _told(app) -> int:
    return sum("Plugin update" in m for m in _messages(app))


def test_a_channel_plugin_is_labelled_as_a_channel():
    telegram = FoundServer("telegram", "Chat on Telegram", "none", [], True, channel=True)
    slack = FoundServer("slack", "Slack", "stdio", [], True, skill=True, channel=True)
    assert Plugin("telegram", False, server=telegram).kind == "Channel"
    assert Plugin("slack", False, server=slack).kind == "MCP server · channel · skill"
    assert "Runs: on the assistant's computer" in describe(Plugin("telegram", False, server=telegram))


def test_a_subagent_plugin_is_labelled_as_one():
    researcher = FoundServer("researcher", "Researches", "none", [], False, subagent="researcher")
    assert Plugin("researcher", False, server=researcher).kind == "Subagent"


def test_a_coding_agent_plugin_is_labelled_as_one_not_as_its_skill():
    claude = FoundServer("claude-code", "Claude Code", "none", [], False, skill=True, agent="claude")
    assert Plugin("claude-code", False, server=claude).kind == "Coding agent · skill"


def test_plugins_are_grouped_by_their_categorys_group_with_other_last():
    def plugin(name: str, category: str) -> Plugin:
        return Plugin(name, False, server=FoundServer(name, "", "stdio", [], False, category=category))

    shown = [
        plugin("misc", "other/general"),
        plugin("ledger", "apps/finance"),
        plugin("bot", "communications/chat"),
        plugin("mail", "communications/email"),
    ]
    assert [(c, [p.name for p in g]) for c, g in by_category(shown)] == [
        ("apps", ["ledger"]),
        ("communications", ["bot", "mail"]),
        ("other", ["misc"]),
    ]
    assert "Category: Apps / Finance" in describe(shown[1])


def test_a_value_the_daemon_already_has_may_be_left_empty():
    token = ServerField("BOT_TOKEN", "Bot token", secret=True)
    telegram = FoundServer("telegram", "Chat on Telegram", "none", [token], True, known_fields=["BOT_TOKEN"])
    assert "leave empty to keep the one you set before" in str(_field_input(telegram, token).placeholder)
    asked = replace(telegram, known_fields=[])
    assert "leave empty" not in str(_field_input(asked, token).placeholder)


def test_an_optional_field_and_the_shared_copilot_login_are_explained():
    from assistant.core.agent import RepositoryContents
    from assistant_terminal.tui.screens.repository_install import _guide

    token = ServerField("CLAUDE_TOKEN", "Claude token", secret=True, optional=True)
    coder = FoundServer(
        "claude-code", "Coding tasks", "stdio", [token], False, steps=["Paste it."], model_login="copilot"
    )
    assert "optional" in str(_field_input(coder, token).placeholder)
    guide = _guide(RepositoryContents(skills=[], servers=[coder]))
    assert guide.startswith("It uses your GitHub Copilot login from /model") and "1. Paste it." in guide
    hosts = FoundServer("hosts", "Your hosts", "stdio", [], False, ssh_agent=True)
    assert "your ssh agent" in _guide(RepositoryContents(skills=[], servers=[hosts]))


async def test_updates_lists_the_newer_plugins_and_updates_the_picked_ones(app, client):
    from textual.widgets import SelectionList

    from assistant_terminal.tui.screens.plugin_updates import PluginUpdatesScreen
    from tests.terminal.conftest import _mcp_status

    updated = []

    async def update(name):
        updated.append(name)

    client.mcp.update_from_repository = update
    for name in ("weather", "radar"):
        client.mcp.items[name] = _mcp_status(name)
    client.repositories.more = [
        FoundServer("radar", "Radar", "stdio", [], False, installed=True, version="2.0.0", installed_version="1.0.0")
    ]
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app)
        updates = screen.query_one("#updates", Button)
        await wait_for(pilot, lambda: updates.display and str(updates.label) == "Updates (2)")
        updates.press()
        await wait_for(pilot, lambda: isinstance(app.screen, PluginUpdatesScreen))
        picks = app.screen.query_one("#plugin-updates-list", SelectionList)
        assert set(picks.selected) == {f"{EXTRAS}|server:weather", f"{EXTRAS}|server:radar"}
        picks.deselect(f"{EXTRAS}|server:radar")
        app.screen.query_one("#update-selected", Button).press()
        await wait_for(pilot, lambda: updated == ["weather"])


async def test_repositories_are_added_and_removed_and_their_plugins_listed(app, client):
    from assistant_terminal.tui.screens.repositories import RepositoriesScreen

    mine = "https://github.com/me/plugins"
    client.repositories.mine = [FoundServer("journal", "My journal", "stdio", [], False, category="other/general")]
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: "Source: Official" in _body(screen))
        screen.query_one("#repositories", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, RepositoriesScreen))
        repositories = app.screen
        listed = repositories.query_one("#repositories-list", OptionList)
        await wait_for(pilot, lambda: listed.option_count == 1)
        assert not repositories.query_one("#remove").display  # the extras can't be removed
        repositories.query_one("#repository-url", Input).value = mine
        repositories.query_one("#add", Button).press()
        await wait_for(pilot, lambda: listed.option_count == 2 and client.repositories.added == [mine])
        repositories.query_one("#close", Button).press()
        await wait_for(pilot, lambda: app.screen is screen)
        screen.query_one("#plugins-search", Input).value = "journal"
        await wait_for(pilot, lambda: "## journal" in _body(screen))
        assert "Source: me/plugins (not official)" in _body(screen)
        screen.query_one("#install", Button).press()
        await wait_for(pilot, lambda: "journal" in client.mcp.items)
        assert client.repositories.installed[-1][0] == mine


async def test_a_repository_that_cant_be_read_is_told(app, client):
    client.repositories.unreachable = True
    async with app.run_test(size=(120, 44)) as pilot:
        await _open(pilot, app)
        await wait_for(pilot, lambda: any("no network" in str(n.message) for n in app._notifications))


async def test_a_private_repository_is_added_with_its_token(app, client):
    from assistant_terminal.tui.screens.repositories import RepositoriesScreen

    private = "https://github.com/me/private"
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        screen.query_one("#repositories", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, RepositoriesScreen))
        repositories = app.screen
        token = repositories.query_one("#repository-token", Input)
        assert token.password
        repositories.query_one("#repository-url", Input).value = private
        token.value = "ghp_secret"
        repositories.query_one("#add", Button).press()
        await wait_for(pilot, lambda: client.repositories.tokens == {private: "ghp_secret"})
        assert token.value == ""


async def test_removing_a_plugin_asks_whether_to_keep_its_keys(app, client):
    from assistant_terminal.tui.screens.kept_keys import KeptKeysScreen

    client.mcp.keeps_keys = True
    client.mcp.items["weather"] = client.mcp.items["notes"]
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        screen.query_one("#plugins-search", Input).value = "weather"
        await wait_for(pilot, lambda: "## weather" in _body(screen) and screen.query_one("#remove").display)
        screen.query_one("#remove", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmWithOptionScreen))
        app.screen.query_one("#confirm-yes", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, KeptKeysScreen))
        assert "API_KEY is kept encrypted" in str(app.screen.query_one("#confirm-question").render())
        app.screen.query_one("#delete", Button).press()
        await wait_for(pilot, lambda: getattr(client.repositories, "forgotten", None) is not None)
        assert client.repositories.forgotten.plugin == "weather"


def test_a_plugin_a_repository_couldnt_read_is_named_with_the_repository():
    extras = Repository(EXTRAS, "lo9i/lo9i-assistant-extras", True)
    mine = Repository("https://github.com/me/plugins", "me/plugins", False)
    read = [
        RepositoryPlugins(extras, RepositoryContents([], [], ["apps/finance/ledger/server.yaml can't be used: bad"])),
        RepositoryPlugins(mine, None, "Couldn't get the repository"),
    ]
    assert from_repositories(read)[1] == [
        "me/plugins: Couldn't get the repository",
        "lo9i/lo9i-assistant-extras: apps/finance/ledger/server.yaml can't be used: bad",
    ]


def _checked(screen) -> str:
    return str(screen.query_one("#plugins-checked").render())


async def test_the_list_shows_at_once_as_last_checked_then_the_repositories_are_checked(app, client):
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: client.repositories.checks_made == 1)
        await wait_for(pilot, lambda: _checked(screen) == "Checked just now")
        assert screen.query_one("#plugins-list", OptionList).option_count == 4
        screen.query_one("#refresh", Button).press()
        await wait_for(pilot, lambda: client.repositories.checks_made == 2)


async def test_a_check_that_cant_reach_the_repositories_keeps_the_list_from_the_last_one(app, client):
    client.repositories.check_fails = True
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: _checked(screen).startswith("Couldn't check for updates · checked"))
        assert screen.query_one("#plugins-list", OptionList).option_count == 4


def test_the_last_check_is_the_oldest_and_none_while_one_never_was():
    from datetime import UTC, datetime

    from assistant_terminal.plugins_text import checked_line, last_checked

    extras = Repository(EXTRAS, "lo9i/lo9i-assistant-extras", True)
    older, newer = "2030-01-01T09:00:00+00:00", "2030-01-01T10:00:00+00:00"
    read = [
        RepositoryPlugins(extras, RepositoryContents([], [], [], newer)),
        RepositoryPlugins(extras, RepositoryContents([], [], [], older)),
    ]
    assert last_checked(read) == older
    assert last_checked([*read, RepositoryPlugins(extras, None, "no network")]) == ""
    now = datetime(2030, 1, 1, 12, tzinfo=UTC)
    assert checked_line(older, False, False, now) == "Checked 3 hours ago"
    assert checked_line("", True, False, now) == "Checking for updates…"


async def test_only_changes_to_plugins_read_them_again_and_an_error_is_told_once(app, client):
    client.repositories.unreachable = True
    read = []
    plugins = client.repositories.plugins

    async def counted(cached=False):
        read.append(cached)
        return await plugins(cached)

    client.repositories.plugins = counted

    def told() -> int:
        return sum("no network" in str(n.message) for n in app._notifications)

    async with app.run_test(size=(120, 44)) as pilot:
        await _open(pilot, app)
        await wait_for(pilot, lambda: len(read) == 2 and told() == 1)
        for kind in ("conversations", "jobs", "notifications", "home", "clients", "update"):
            await client.bus.put((kind, {}))
        await pilot.pause(0.2)
        assert len(read) == 2
        await client.bus.put(("plugins", {}))
        await wait_for(pilot, lambda: len(read) == 3)
        await pilot.pause(0.1)
        assert told() == 1


async def test_reading_the_plugins_again_doesnt_hold_up_the_other_events(app, client):
    from assistant.core.events import Done, TextDelta
    from assistant_terminal.tui.widgets import AssistantMessage

    # Set while the list reads at once; cleared, the next read waits.
    reading = asyncio.Event()
    reading.set()
    plugins = client.repositories.plugins

    async def slow(cached=False):
        if cached:
            await reading.wait()
        return await plugins(cached)

    async def elsewhere():
        yield TextDelta("Done there.")
        yield Done()

    client.repositories.plugins = slow
    client.runs["r1"] = elsewhere
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: screen.query_one("#plugins-list", OptionList).option_count == 4)
        reading.clear()
        await client.bus.put(("plugins", {}))
        run = {"run_id": "r1", "thread_id": "owner:abc", "channel": "web", "client_id": "other", "text": "hi"}
        await client.bus.put(("run", run))
        try:
            await wait_for(pilot, lambda: app.query(AssistantMessage))
        finally:
            reading.set()


async def test_an_installed_plugins_settings_change_what_it_was_given(app, client):
    client.mcp.items["calendar"] = _mcp_status("calendar", source=EXTRAS)
    async with app.run_test(size=(120, 50)) as pilot:
        screen = await _open(pilot, app)
        screen.query_one("#plugins-search", Input).value = "calendar"
        await wait_for(pilot, lambda: "## calendar" in _body(screen) and screen.query_one("#plugin-settings").display)
        screen.query_one("#plugin-settings", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, PluginSettingsScreen))
        settings = app.screen
        await wait_for(pilot, lambda: bool(settings.query("#plugin-field-CAL_USER")))
        user = settings.query_one("#plugin-field-CAL_USER", Input)
        password = settings.query_one("#plugin-field-CAL_PASSWORD", Input)
        # A field not secret shows its value; a secret one only that it's saved, and only an optional one clears.
        assert user.value == "me" and password.value == "" and password.password
        assert password.placeholder == "Saved: leave empty to keep it"
        assert not settings.query("#plugin-clear-CAL_PASSWORD") and settings.query("#plugin-clear-CAL_PIN")
        message = settings.query_one("#plugin-settings-message", Markdown)
        assert "It checks what you enter before it's saved" in message.source
        # What its check says shows here, and nothing closes.
        client.mcp.check_refusal = "calendar: The server refused the password."
        user.value = "you"
        settings.query_one("#save", Button).press()
        await wait_for(pilot, lambda: "The server refused the password." in message.source)
        assert app.screen is settings and client.mcp.saved_settings is None
        client.mcp.check_refusal = ""
        settings.query_one("#plugin-clear-CAL_PIN", Checkbox).value = True
        settings.query_one("#save", Button).press()
        await wait_for(pilot, lambda: app.screen is screen)
        # The secret left empty isn't sent, which keeps it.
        assert client.mcp.saved_settings == ("calendar", {"CAL_USER": "you"}, ["CAL_PIN"])


async def test_a_plugin_not_installed_has_no_settings(app, client):
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app)
        screen.query_one("#plugins-search", Input).value = "calendar"
        await wait_for(pilot, lambda: "## calendar" in _body(screen))
        assert not screen.query_one("#plugin-settings").display
