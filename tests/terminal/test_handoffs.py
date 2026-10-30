from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Button, Input, OptionList

from assistant.core.agent import ShownMessage
from assistant.core.events import Cancelled, UserSaid, UserTaken
from assistant_terminal.tui.history import Loaders, show_history
from assistant_terminal.tui.screens import AgentFolderScreen
from assistant_terminal.tui.turn import TurnView
from assistant_terminal.tui.widgets import StatusLine, UserMessage
from tests.terminal.conftest import wait_for


async def test_claude_hands_the_conversation_over_and_off_takes_it_back(app, client):
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: "/claude" in app._agents)
        await pilot.press("ctrl+n")
        await wait_for(pilot, lambda: app.sub_title == "new conversation")
        thread_id = app._live.session.thread_id
        await pilot.click("#prompt")
        await pilot.press(*"/claude relative", "enter")
        await wait_for(pilot, lambda: any("isn't an existing folder" in n.message for n in app._notifications))
        await pilot.press(*"/claude /tmp/repo", "enter")
        await wait_for(pilot, lambda: app.sub_title == "new conversation · talking to Claude Code in /tmp/repo")
        assert client.conversations.handoffs[thread_id].folder == "/tmp/repo"
        await pilot.press(*"/claude off", "enter")
        await wait_for(pilot, lambda: app.sub_title == "new conversation")


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
        thread_id = "owner:new"  # the app is on the inbox, which hands a new conversation
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
        thread_id = "owner:new"  # the app is on the inbox, which hands a new conversation
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


async def test_hidden_folders_show_only_after_show_hidden(app, client):
    async with app.run_test() as pilot:
        await wait_for(pilot, lambda: "/claude" in app._agents)
        await pilot.click("#prompt")
        await pilot.press(*"/claude", "enter", "enter")
        await wait_for(pilot, lambda: "Browse…" in _options(app))
        await pilot.press("end", "enter")
        await wait_for(pilot, lambda: "projects/" in _options(app))
        assert ".config/" not in _options(app)
        app.screen.query_one("#hidden", Button).press()
        await wait_for(pilot, lambda: ".config/" in _options(app))
        assert str(app.screen.query_one("#hidden", Button).label) == "Hide hidden"
        app.screen.query_one("#hidden", Button).press()
        await wait_for(pilot, lambda: ".config/" not in _options(app))


def _options(app) -> list[str]:
    if not isinstance(app.screen, AgentFolderScreen):
        return []
    shown = app.screen.query_one("#agent-folder-options", OptionList)
    return [str(shown.get_option_at_index(i).prompt) for i in range(shown.option_count)]


class _Chat(App):
    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="chat")
        yield StatusLine()


async def _events(*events):
    for event in events:
        yield event


async def test_a_message_the_agent_gets_to_later_says_its_waiting_until_it_takes_it():
    app = _Chat()
    async with app.run_test():
        view = TurnView(app.query_one("#chat", VerticalScroll), app.query_one(StatusLine))
        await view.render(_events(UserSaid("docs", id="m1", waiting=True), UserSaid("tests", id="m2", waiting=True)))
        shown = [str(m.render()) for m in app.query(UserMessage)]
        assert shown == [
            "> docs\n  waiting for the agent to get to it",
            "> tests\n  waiting for the agent to get to it",
        ]
        await view.render(_events(UserTaken("m1"), Cancelled()))
        shown = [str(m.render()) for m in app.query(UserMessage)]
        assert shown == ["> docs", "> tests\n  not taken: sent again below"]  # it went to the agent next


async def test_history_shows_a_message_it_never_got_to_and_those_sent_again():
    app = _Chat()
    async with app.run_test():
        await show_history(
            app.query_one("#chat", VerticalScroll),
            [ShownMessage("user", "tests", untaken=True), ShownMessage("user", "tests", resent=True)],
            Loaders(_never, _never),
        )
        shown = [str(m.render()) for m in app.query(UserMessage)]
        assert shown == ["> tests\n  not taken: sent again below", "> tests\n  sent again"]


async def _never(*_):
    raise AssertionError("nothing to load")
