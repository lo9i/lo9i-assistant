"""The navigation on the left: the chat and every page show it, picking a page opens it in the chat's place and Chat
goes back, Settings shows its sections as tabs, the conversations open here show under Chat with what they're doing,
counts show beside the pages, and F4 collapses it to its glyphs, kept for the next start."""

from textual.widgets import Tab, Tabs

from assistant.core.agent import Conversation
from assistant.core.events import ApprovalRequired
from assistant_terminal.nav import OPEN, SETTINGS_TABS
from assistant_terminal.preferences import Preferences
from assistant_terminal.tui.page import PageScreen
from assistant_terminal.tui.screens import (
    BriefingSection,
    EmailRecipientsSection,
    LanguageSection,
    ModelSection,
    NotificationsScreen,
    PluginsSection,
    SettingsScreen,
)
from assistant_terminal.tui.sidebar import Sidebar
from tests.terminal.conftest import section_shown, wait_for, wait_for_section

_AT = "2030-01-01T09:00:00+00:00"


def _lines(sidebar: Sidebar) -> list[str]:
    return [str(sidebar.get_option_at_index(n).prompt) for n in range(sidebar.option_count)]


def _pick(sidebar: Sidebar, key: str) -> None:
    sidebar.highlighted = sidebar.get_option_index(key)
    sidebar.action_select()


async def test_a_page_opens_beside_the_sidebar_and_chat_goes_back(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        sidebar = app.screen.query_one(Sidebar)
        assert "⌂ Home" in _lines(sidebar) and "✱ Settings" in _lines(sidebar)
        _pick(sidebar, "notifications")
        await wait_for(pilot, lambda: isinstance(app.screen, NotificationsScreen))
        page_sidebar, listed = app.screen.query_one(Sidebar), app.screen.query_one("#notifications-list")
        await wait_for(pilot, lambda: listed.has_focus)  # the page's own list, not the sidebar
        assert page_sidebar.highlighted_option is not None and page_sidebar.highlighted_option.id == "notifications"
        _pick(page_sidebar, "jobs")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "JobsScreen")
        assert sum(isinstance(s, PageScreen) for s in app.screen_stack) == 1  # in the last one's place
        _pick(app.screen.query_one(Sidebar), "chat")
        await wait_for(pilot, lambda: app.screen is app.screen_stack[0] and app.focused is app.query_one("#prompt"))


async def test_a_slash_command_opens_its_page_and_esc_goes_back(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/notifications", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, NotificationsScreen))
        assert app.screen.query(Sidebar)
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is app.screen_stack[0])


async def test_settings_shows_its_sections_as_tabs(app, client):
    async with app.run_test(size=(160, 40)) as pilot:
        _pick(app.screen.query_one(Sidebar), "settings")
        language = await wait_for_section(pilot, app, LanguageSection)
        settings = app.screen
        assert isinstance(settings, SettingsScreen)
        sidebar = settings.query_one(Sidebar)
        assert sidebar.highlighted_option is not None and sidebar.highlighted_option.id == "settings"
        assert not any(line.startswith("   ") for line in _lines(sidebar))  # no sections under Settings any more
        tabs = settings.query_one(Tabs)
        assert [str(tab.label) for tab in tabs.query(Tab)] == [tab.label for tab in SETTINGS_TABS]
        await wait_for(pilot, lambda: tabs.has_focus)  # ← and → move between sections from the start
        await pilot.press("right")
        await wait_for_section(pilot, app, BriefingSection)
        await pilot.press("tab")
        await wait_for(pilot, lambda: app.focused is not None and settings.shown == "briefing")
        assert app.focused is not tabs and app.focused in settings.query_one(BriefingSection).query("*")
        await pilot.press("shift+tab", "left")
        assert await wait_for_section(pilot, app, LanguageSection) is language  # built once, kept
        await pilot.click("#--content-tab-settings-email")
        await wait_for_section(pilot, app, EmailRecipientsSection)
        assert app.screen is settings


async def test_a_sections_command_shows_its_tab_on_the_settings_shown(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/model", "enter")
        await wait_for_section(pilot, app, ModelSection)
        settings = app.screen
        await app._commands["/plugins"]("")
        await wait_for_section(pilot, app, PluginsSection)
        assert app.screen is settings and sum(isinstance(s, PageScreen) for s in app.screen_stack) == 1
        _pick(settings.query_one(Sidebar), "settings")  # stays on the section shown
        await pilot.pause()
        assert section_shown(app, PluginsSection) is not None
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is app.screen_stack[0])


async def test_the_language_page_sets_it(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/language", "enter", "enter")  # the first completes it: it takes a language too
        await wait_for_section(pilot, app, LanguageSection)
        choices = app.screen.query_one("#language-choices")
        await wait_for(pilot, lambda: choices.option_count == 3)
        await pilot.press("tab")  # from the tabs into the section
        await wait_for(pilot, lambda: choices.has_focus)
        await pilot.press("down", "down", "enter")
        await wait_for(pilot, lambda: client.language.current == "es")
        assert str(choices.get_option_at_index(2).prompt) == "● Español"


async def test_open_conversations_show_under_chat_with_what_they_do(app, client):
    client.conversations.items += [
        Conversation("owner:b", "clean up", _AT, _AT),
        Conversation("owner:c", "trip", _AT, _AT),
    ]
    client.conversations.waiting["owner:b"] = [ApprovalRequired("i9", {"tool": "bash", "command": "ls"})]
    async with app.run_test(size=(120, 40)) as pilot:
        app._opened.extend(["owner:b", "owner:c"])
        app.refresh_nav()
        sidebar = app.screen.query_one(Sidebar)
        await wait_for(pilot, lambda: "  ◉ clean up" in _lines(sidebar) and "  ○ trip" in _lines(sidebar))
        assert "✎ Chat  1" in _lines(sidebar)  # one waits for an answer
        _pick(sidebar, OPEN + "owner:c")
        await wait_for(pilot, lambda: app._live.session.thread_id == "owner:c")


async def test_unread_notifications_are_counted_beside_their_page(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        sidebar = app.screen.query_one(Sidebar)
        await wait_for(pilot, lambda: "✉ Notifications  2" in _lines(sidebar))


async def test_f4_collapses_it_to_glyphs_on_every_page_and_keeps_it(app, client, tmp_path):
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("f4")
        sidebar = app.screen.query_one(Sidebar)
        await wait_for(pilot, lambda: sidebar.collapsed and _lines(sidebar)[0] == "⌂ ")
        assert sidebar.outer_size.width == 5
        await pilot.click("#prompt")
        await pilot.press(*"/jobs", "enter")
        await wait_for(pilot, lambda: type(app.screen).__name__ == "JobsScreen")
        assert app.screen.query_one(Sidebar).collapsed
        await pilot.press("f4")
        await wait_for(pilot, lambda: not app.screen.query_one(Sidebar).collapsed)
        assert not app.screen_stack[0].query_one(Sidebar).collapsed
    assert not Preferences(tmp_path / "cli_preferences.json").sidebar_collapsed


async def test_f5_moves_to_the_sidebar_and_back(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        prompt = app.query_one("#prompt")
        await pilot.click("#prompt")
        await pilot.press("f5")
        await wait_for(pilot, lambda: app.focused is app.screen.query_one(Sidebar))
        await pilot.press("f5")
        await wait_for(pilot, lambda: app.focused is prompt)
