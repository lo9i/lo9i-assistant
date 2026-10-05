from textual.widgets import Input, Markdown, OptionList, Select

from assistant_terminal.tui.screens import ProfileScreen
from tests.terminal.conftest import wait_for


async def test_add_edit_and_remove_profile_items(app, client):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/profile", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ProfileScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#profile-body", Markdown).source

        await wait_for(pilot, lambda: "0 of 8 items" in body())
        screen.query_one("#profile-section", Select).value = "goals"
        prompt = screen.query_one("#profile-input", Input)
        prompt.focus()
        prompt.value = "Run a marathon"
        await pilot.press("enter")
        await wait_for(pilot, lambda: client.memory.profile.get("goals") == ["Run a marathon"])

        items = screen.query_one("#profile-items", OptionList)
        items.focus()
        items.highlighted = 0
        await pilot.press("enter")
        await wait_for(pilot, lambda: prompt.value == "Run a marathon")
        prompt.value = "Run a half marathon"
        await pilot.press("enter")
        await wait_for(pilot, lambda: client.memory.profile["goals"] == ["Run a half marathon"])

        items.focus()
        items.highlighted = 0
        await pilot.press("delete")
        await wait_for(pilot, lambda: client.memory.profile["goals"] == [])


async def test_a_full_section_takes_no_more_items(app, client):
    client.memory.profile = {"about": [f"item {i}" for i in range(8)]}
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/profile", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ProfileScreen))
        screen = app.screen
        prompt = screen.query_one("#profile-input", Input)
        prompt.focus()
        prompt.value = "one more"
        await pilot.press("enter")
        await wait_for(pilot, lambda: "full" in screen.query_one("#profile-body", Markdown).source)
        assert len(client.memory.profile["about"]) == 8


async def test_saved_facts_are_edited_and_deleted_after_confirming(app, client):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/profile", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ProfileScreen))
        screen = app.screen
        screen.query_one("#profile-section", Select).value = "saved:facts"
        await wait_for(pilot, lambda: "1 saved." in screen.query_one("#profile-body", Markdown).source)

        prompt = screen.query_one("#profile-input", Input)
        prompt.focus()
        prompt.value = "something new"
        await pilot.press("enter")
        await wait_for(pilot, lambda: "Pick one to edit it" in screen.query_one("#profile-body", Markdown).source)
        assert [f.text for f in client.memory.saved_facts] == ["likes jazz"]  # nothing added

        items = screen.query_one("#profile-items", OptionList)
        items.focus()
        items.highlighted = 0
        await pilot.press("enter")
        await wait_for(pilot, lambda: prompt.value == "likes jazz")
        prompt.value = "likes jazz and blues"
        await pilot.press("enter")
        await wait_for(pilot, lambda: [f.text for f in client.memory.saved_facts] == ["likes jazz and blues"])

        items.focus()
        items.highlighted = 0
        await pilot.press("delete")
        await wait_for(pilot, lambda: app.screen is not screen)
        await pilot.press("y")
        await wait_for(pilot, lambda: client.memory.saved_facts == [])
