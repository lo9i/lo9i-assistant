from textual.widgets import Input, Markdown

from assistant.core.agent import SlackStatus
from assistant_terminal.tui.screens import SlackScreen
from tests.terminal.conftest import wait_for


async def test_connect_with_three_tokens_then_running(app, client):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/slack", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, SlackScreen))

        def body() -> str:
            return app.screen.query_one("#slack-body", Markdown).source

        await wait_for(pilot, lambda: "From a manifest" in body())
        app.screen.query_one("#slack-app-token", Input).value = "xapp-bad"
        await pilot.press("enter")
        await wait_for(pilot, lambda: "Paste all three tokens" in body())
        app.screen.query_one("#slack-bot-token", Input).value = "xoxb-1"
        app.screen.query_one("#slack-user-token", Input).value = "xoxp-1"
        await pilot.press("enter")
        await wait_for(pilot, lambda: "invalid_auth" in body())
        app.screen.query_one("#slack-app-token", Input).value = "xapp-1"
        await pilot.press("enter")
        await wait_for(pilot, lambda: "Slack: Acme" in body() and "not open" in body())
        client.slack.state = SlackStatus(True, True, "Acme", "ani")
        await client.bus.put(("integrations", {}))  # the adapter connected
        await wait_for(pilot, lambda: "open ✓" in body())
        await pilot.press("escape")
        await wait_for(pilot, lambda: not isinstance(app.screen, SlackScreen))
