from textual.widgets import Button, Checkbox, Markdown, OptionList, SelectionList, Static

from assistant.core.agent import Skill
from assistant_terminal.tui.screens import ConfirmScreen, SkillImportsScreen, SkillsScreen, UsageScreen
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


async def test_skills_screen_shows_failing_skills_and_problems(app, client):
    client.skills.failures["news-digest"] = (3, "exit code: 1", "2026-10-03T12:00:00+00:00", True)
    client.skills.items["weekly-review"] = Skill(
        "weekly-review", "Friday", "Run scripts/a.py", problems=["Missing a.py."]
    )
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "/skills", SkillsScreen)
        options = screen.query_one("#skills-list", OptionList)
        await wait_for(pilot, lambda: "Failed 3 times in a row" in screen.query_one("#skill-body", Markdown).source)
        assert str(options.get_option_at_index(0).prompt) == "news-digest · failing"
        assert str(options.get_option_at_index(1).prompt) == "weekly-review · has problems"
        options.highlighted = 1
        await wait_for(pilot, lambda: "**Problem:** Missing a.py." in screen.query_one("#skill-body", Markdown).source)


async def test_usage_screen_shows_tools_and_skills(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "/usage", UsageScreen)

        def body() -> str:
            return screen.query_one("#usage-body", Markdown).source

        await wait_for(pilot, lambda: "| bash | 12 | 1 | 2 | 850 ms |" in body() and "| news-digest | 3 |" in body())
        assert "4 model calls · 52.0k in (40.0k from the cache) · 1.8k out · $0.07" in body()
        assert (
            "| claude-opus-5-5 | 4 | 52.0k | 40.0k | 1.8k | $0.07 |" in body()
            and "| web_fetch | 1 | 9.0k | 40 |" in body()
        )
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


async def test_a_skill_installed_from_the_extras_is_updated_here(app, client):
    from assistant.core.repositories.known import EXTRAS

    async with app.run_test(size=(120, 50)) as pilot:
        screen = await _open(pilot, app, "/skills", SkillsScreen)
        assert not screen.query("#install")  # the extras are installed from /plugins
        await client.repositories.install(["expenses"], [])
        await screen.reload()

        def body() -> str:
            return screen.query_one("#skill-body", Markdown).source

        screen.query_one("#skills-list", OptionList).highlighted = 2
        await wait_for(pilot, lambda: f"Installed from** {EXTRAS}" in body())
        screen.query_one("#update", Button).press()
        await wait_for(pilot, lambda: getattr(client.skills, "updated", None) == "expenses")


async def test_import_skills_lists_other_agents_skills_and_imports_the_picked_ones(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app, "/import-skills", SkillImportsScreen)
        options = screen.query_one("#skill-imports-list", SelectionList)
        await wait_for(pilot, lambda: options.option_count == 2)
        assert str(options.get_option_at_index(1).prompt) == "edit (Codex) · for a coding agent"
        assert "CLAUDE.md" in str(screen.query_one("#skill-imports-suggestions", Static).render())
        assert options.selected == []
        options.select("/h/.agents/skills/edit")
        screen.query_one("#replace", Checkbox).value = True
        screen.query_one("#import", Button).press()
        await wait_for(pilot, lambda: client.skills.imports == [(["/h/.agents/skills/edit"], True)])
