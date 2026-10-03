from tests.terminal.conftest import wait_for


async def test_name_command_and_title_follow_renames(app, client):
    async with app.run_test() as pilot:
        assert app.title == "lo9i assistant"
        await pilot.click("#prompt")
        await pilot.press(*"/name Max", "enter")
        await wait_for(pilot, lambda: client.identity.current == "Max")
        assert any("Renamed to Max" in n.message for n in app._notifications)
        client.identity.current = "Ada"  # renamed by asking, from Telegram
        await client.bus.put(("settings", {}))
        await wait_for(pilot, lambda: app.title == "Ada")
