"""/use: the conversation answers with another model from the next message; the subtitle names it, and a note shows
in the conversation when the change left one."""

from lo9i_terminal.tui.widgets import ModelChangedNote
from tests.terminal.conftest import wait_for


async def test_use_names_the_model_under_the_title_and_main_goes_back(app, client):
    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        thread_id = "owner:new"
        await wait_for(pilot, lambda: app.sub_title == "new conversation")
        await pilot.click("#prompt")
        await pilot.press(*"/use fast-1", "enter")
        await wait_for(pilot, lambda: client.conversations.picked.get(thread_id) == "fast-1")
        assert any("answers with Fast" in n.message for n in app._notifications)
        await client.bus.put(("conversation_model", {"thread_id": thread_id, "noted": False, "name": "Fast"}))
        await wait_for(pilot, lambda: app.sub_title == "new conversation · model: Fast")
        await pilot.press(*"/use main", "enter")
        await wait_for(pilot, lambda: client.conversations.picked[thread_id] == "")
        await client.bus.put(("conversation_model", {"thread_id": thread_id, "noted": False, "name": "Main One"}))
        await wait_for(pilot, lambda: app.sub_title == "new conversation")


async def test_use_alone_picks_from_a_list_and_a_note_shows_when_one_was_left(app, client):
    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        thread_id = "owner:new"
        await wait_for(pilot, lambda: app.sub_title == "new conversation")
        await pilot.click("#prompt")
        await pilot.press(*"/use", "enter")
        await wait_for(pilot, lambda: app.screen.query("#question-options"))
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: client.conversations.picked.get(thread_id) == "fast-1")
        await client.bus.put(("conversation_model", {"thread_id": thread_id, "noted": True, "name": "Fast"}))
        await wait_for(pilot, lambda: app.query(ModelChangedNote))


async def test_an_unknown_model_is_reported(app, client):
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/use nope", "enter")
        await wait_for(pilot, lambda: any("isn't a model" in n.message for n in app._notifications))
