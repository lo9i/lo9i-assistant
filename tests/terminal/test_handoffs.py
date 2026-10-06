from textual.widgets import Input, OptionList

from assistant_terminal.tui.screens import AgentFolderScreen
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


async def test_claude_alone_picks_a_folder_used_before(app, client):
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: "/claude" in app._agents)
        thread_id = app._live.session.thread_id
        await pilot.click("#prompt")
        await pilot.press(*"/claude", "enter", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, AgentFolderScreen))
        await wait_for(
            pilot,
            lambda: _options(app) == ["Workspace  /home/me/.lo9i/claude-workspace", "/home/me/projects/app", "Browse…"],
        )
        await pilot.press("down", "enter")
        await wait_for(pilot, lambda: thread_id in client.conversations.handoffs)
        assert client.conversations.handoffs[thread_id].folder == "/home/me/projects/app"


async def test_claude_alone_browses_to_a_new_project(app, client):
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: "/claude" in app._agents)
        thread_id = app._live.session.thread_id
        await pilot.click("#prompt")
        await pilot.press(*"/claude", "enter", "enter")
        await wait_for(pilot, lambda: "Browse…" in _options(app))
        await pilot.press("end", "enter")
        await wait_for(pilot, lambda: "projects/" in _options(app))
        await pilot.press("down", "down", "enter")
        await wait_for(pilot, lambda: "new/" in _options(app))
        await pilot.press("down", "down", "down", "enter")
        await wait_for(pilot, lambda: _options(app)[:2] == ["Use this folder", ".. up"] and len(_options(app)) == 2)
        await pilot.press("enter")
        await wait_for(pilot, lambda: thread_id in client.conversations.handoffs)
        assert client.conversations.handoffs[thread_id].folder == "/home/me/projects/new"


def _options(app) -> list[str]:
    if not isinstance(app.screen, AgentFolderScreen):
        return []
    shown = app.screen.query_one("#agent-folder-options", OptionList)
    return [str(shown.get_option_at_index(i).prompt) for i in range(shown.option_count)]
