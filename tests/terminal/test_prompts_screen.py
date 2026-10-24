"""/prompt: the system prompt texts, edited, saved and reset as in the web app's Settings → System prompt."""

from textual.widgets import Button, OptionList, Static, TextArea

from assistant_terminal.tui.screens import ConfirmScreen, PromptsScreen
from tests.terminal.conftest import wait_for


async def _open(pilot, app) -> PromptsScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/prompt", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, PromptsScreen))
    return app.screen


async def test_a_text_is_edited_saved_and_reset(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app)
        area = screen.query_one("#prompt-text", TextArea)
        await wait_for(pilot, lambda: area.text == "You are the assistant.")
        options = screen.query_one("#prompts-list", OptionList)
        assert [str(options.get_option_at_index(i).prompt) for i in range(3)] == [
            "Persona",
            "Operating instructions",
            "Channels",
        ]
        assert screen.query_one("#reset", Button).disabled
        area.load_text("You are Lo9i.")
        screen.query_one("#save", Button).press()
        await wait_for(pilot, lambda: client.prompts.items["persona"].edited)
        await wait_for(pilot, lambda: not screen.query_one("#reset", Button).disabled)
        assert "Edited." in str(screen.query_one("#prompt-about", Static).render())
        screen.query_one("#reset", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(
            pilot, lambda: not client.prompts.items["persona"].edited and area.text == "You are the assistant."
        )


async def test_an_empty_text_isnt_saved_and_unsaved_text_is_kept_across_texts(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app)
        area = screen.query_one("#prompt-text", TextArea)
        await wait_for(pilot, lambda: area.text == "You are the assistant.")
        area.load_text(" ")
        screen.query_one("#save", Button).press()
        await pilot.pause()
        assert not client.prompts.items["persona"].edited
        area.load_text("A draft.")
        await pilot.pause()
        screen.query_one("#prompts-list", OptionList).highlighted = 1
        await wait_for(pilot, lambda: area.text == "Work carefully.")
        screen.query_one("#prompts-list", OptionList).highlighted = 0
        await wait_for(pilot, lambda: area.text == "A draft.")
        await pilot.press("escape")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: not isinstance(app.screen, (PromptsScreen, ConfirmScreen)))


async def test_a_change_of_the_built_in_text_is_shown_until_the_edit_is_kept(app, client):
    from dataclasses import replace

    persona = client.prompts.items["persona"]
    changes = "--- when you edited it\n+++ now\n+Be kind."
    client.prompts.items["persona"] = replace(persona, text="You are Lo9i.", edited=True, built_in_changes=changes)
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app)
        shown = screen.query_one("#prompt-changes", Static)
        await wait_for(pilot, lambda: "+Be kind." in str(shown.render()) and shown.display)
        screen.query_one("#keep", Button).press()
        await wait_for(pilot, lambda: not client.prompts.items["persona"].built_in_changes and not shown.display)
        assert not screen.query_one("#keep").display
