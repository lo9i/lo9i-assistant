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


async def test_skills_and_servers_are_installed_from_a_repository(app, client):
    from textual.widgets import Input, SelectionList

    from assistant_terminal.tui.screens.repository_install import RepositoryInstallScreen

    async with app.run_test(size=(120, 50)) as pilot:
        screen = await _open(pilot, app, "/skills", SkillsScreen)
        screen.query_one("#install", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, RepositoryInstallScreen))
        install = app.screen

        def message() -> str:
            return install.query_one("#repository-message", Markdown).source

        install.query_one("#repository-url", Input).value = "file:///tmp/x"
        install.query_one("#browse", Button).press()
        await wait_for(pilot, lambda: "https://" in message())
        install.query_one("#repository-url", Input).value = "https://example.com/extras"
        install.query_one("#browse", Button).press()
        found = install.query_one("#repository-found", SelectionList)
        await wait_for(pilot, lambda: found.option_count == 2)
        fields = list(install.query("#repository-fields Input").results(Input))
        assert [f.password for f in fields] == [False, True] and not any(f.display for f in fields)
        found.select("skill:expenses")
        found.select("server:calendar")
        await wait_for(pilot, lambda: all(f.display for f in fields))
        fields[0].value = "ana"
        install.query_one("#install", Button).press()
        await wait_for(pilot, lambda: "needs Password" in message())
        fields[1].value = "s3cret"
        install.query_one("#install", Button).press()
        await wait_for(pilot, lambda: app.screen is screen and "expenses" in client.skills.items)
        [(_, skills, [server])] = client.repositories.installed
        assert skills == ["expenses"] and server.values == {"CAL_USER": "ana", "CAL_PASSWORD": "s3cret"}

        def body() -> str:
            return screen.query_one("#skill-body", Markdown).source

        screen.query_one("#skills-list", OptionList).highlighted = 2
        await wait_for(pilot, lambda: "Installed from** https://example.com/extras" in body())
        screen.query_one("#update", Button).press()
        await wait_for(pilot, lambda: getattr(client.skills, "updated", None) == "expenses")
