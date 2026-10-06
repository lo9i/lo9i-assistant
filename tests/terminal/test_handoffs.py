from textual.widgets import Input

from tests.terminal.conftest import wait_for


async def test_claude_hands_the_conversation_over_and_off_takes_it_back(app, client):
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: "/claude" in app._agents)
        thread_id = app._live.session.thread_id
        await pilot.click("#prompt")
        await pilot.press(*"/claude relative", "enter")
        await wait_for(pilot, lambda: any("isn't an existing folder" in n.message for n in app._notifications))
        await pilot.press(*"/claude /tmp/repo", "enter")
        await wait_for(pilot, lambda: app.sub_title == f"{thread_id} · talking to Claude Code in /tmp/repo")
        assert client.conversations.handoffs[thread_id].folder == "/tmp/repo"
        await pilot.press(*"/claude off", "enter")
        await wait_for(pilot, lambda: app.sub_title == thread_id)


async def test_the_command_menu_offers_the_agents_command(app, client):
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: "/claude" in app._agents)
        await pilot.click("#prompt")
        await pilot.press(*"/cla")
        menu = app.query_one("#command-menu")
        await wait_for(pilot, lambda: menu.highlighted is not None and menu.highlighted.name == "/claude")
        assert app.query_one("#prompt", Input).value == "/cla"
