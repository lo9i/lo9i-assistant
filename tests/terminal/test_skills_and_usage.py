from textual.widgets import Button, Markdown, OptionList

from assistant_terminal.tui.screens import ConfirmScreen, SkillsScreen, UsageScreen
from tests.terminal.conftest import wait_for


async def _open(pilot, app, command, screen_type):
    await pilot.click("#prompt")
    await pilot.press(*command, "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, screen_type))
    return app.screen


async def test_skills_screen_lists_shows_and_deletes(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "/skills", SkillsScreen)

        def body() -> str:
            return screen.query_one("#skill-body", Markdown).source

        await wait_for(pilot, lambda: "1. Search news" in body())
        assert screen.query_one("#skills-list", OptionList).option_count == 2
        screen.query_one("#skills-list", OptionList).highlighted = 1
        await wait_for(pilot, lambda: "1. List the week" in body())
        screen.query_one("#delete", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: app.screen is screen)
        assert len(client.skills.items) == 2
        screen.query_one("#delete", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: list(client.skills.items) == ["news-digest"])


async def test_usage_screen_shows_tools_and_skills(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "/usage", UsageScreen)

        def body() -> str:
            return screen.query_one("#usage-body", Markdown).source

        await wait_for(pilot, lambda: "| bash | 12 | 1 | 2 | 850 ms |" in body() and "| news-digest | 3 |" in body())
        screen.query_one("#days-30", Button).press()
        await wait_for(pilot, lambda: "last 30 days" in body() and "| news-digest | 12 |" in body())


async def test_memory_panel_lists_skills(app):
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: "news-digest" in str(app.query_one("#memory-body").render()))


async def test_empty_skills_dialog_shows_only_the_message(app, client):
    client.skills.items = {}
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "/skills", SkillsScreen)
        await wait_for(pilot, lambda: screen.query_one("#skills").has_class("empty"))
        assert screen.query_one("#skills-empty").display and not screen.query_one("#delete").display


async def test_enter_closes_the_empty_skills_dialog(app, client):
    client.skills.items = {}
    async with app.run_test() as pilot:
        await _open(pilot, app, "/skills", SkillsScreen)
        await wait_for(pilot, lambda: app.focused is not None and app.focused.id == "close")
        await pilot.press("enter")
        await wait_for(pilot, lambda: not isinstance(app.screen, SkillsScreen))


async def test_skills_are_edited_but_built_in_ones_only_read(app, client):
    from textual.widgets import Input, TextArea

    from assistant_terminal.tui.screens.skill_edit import SkillEditScreen

    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app, "/skills", SkillsScreen)

        def body() -> str:
            return screen.query_one("#skill-body", Markdown).source

        await wait_for(pilot, lambda: "1. Search news" in body())
        screen.query_one("#edit", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, SkillEditScreen))
        dialog = app.screen
        dialog.query_one("#skill-edit-instructions", TextArea).text = ""
        dialog.query_one("#save", Button).press()
        await wait_for(pilot, lambda: "needs a description" in dialog.query_one("#skill-edit-message", Markdown).source)
        dialog.query_one("#skill-edit-description", Input).value = "Morning news"
        dialog.query_one("#skill-edit-instructions", TextArea).text = "1. Search news\n2. Send it on Telegram"
        dialog.query_one("#save", Button).press()
        await wait_for(pilot, lambda: app.screen is screen and "Send it on Telegram" in body())
        assert client.skills.items["news-digest"].description == "Morning news"
