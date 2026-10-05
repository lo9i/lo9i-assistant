from tests.terminal.conftest import wait_for


async def test_pin_and_unpin_show_the_pinned_skills_under_the_title(app, client):
    async with app.run_test() as pilot:
        thread_id = app.sub_title
        await pilot.click("#prompt")
        await pilot.press(*"/pin coding", "enter")
        await wait_for(pilot, lambda: client.conversations.pins.get(thread_id) == ["coding"])
        assert any("Pinned coding" in n.message for n in app._notifications)
        await client.bus.put(("pinned_skills", {}))
        await wait_for(pilot, lambda: app.sub_title == f"{thread_id} · pinned: coding")
        await pilot.press(*"/unpin coding", "enter")
        await wait_for(pilot, lambda: client.conversations.pins[thread_id] == [])
        await client.bus.put(("pinned_skills", {}))
        await wait_for(pilot, lambda: app.sub_title == thread_id)


async def test_pinning_an_unknown_skill_is_reported(app, client):
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/pin nope", "enter")
        await wait_for(pilot, lambda: any("No skill named nope" in n.message for n in app._notifications))
