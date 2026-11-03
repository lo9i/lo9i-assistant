"""/briefing: the latest briefing, an open loop closed with its kind muted and the kind suggested again, the settings,
and a briefing written now."""

from textual.widgets import Button, Input, Markdown, OptionList, Switch

from assistant_terminal.tui.screens import BriefingScreen
from tests.terminal.conftest import wait_for


async def test_the_briefing_shows_loops_closes_them_and_changes_the_settings(app, client):
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/briefing", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, BriefingScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#briefing-body", Markdown).source

        await wait_for(pilot, lambda: "Gas due Thu." in body() and "Sent to telegram" in body())
        listed = screen.query_one("#briefing-list", OptionList)
        listed.highlighted = 2
        await wait_for(pilot, lambda: "## Pay the gas bill" in body() and screen.query_one("#stop").display)
        screen.query_one("#stop", Button).press()
        await wait_for(pilot, lambda: client.proactive.settings.muted == ["bill due"])
        await wait_for(pilot, lambda: "Muted: bill due" in str(listed.get_option_at_index(2).prompt))
        listed.highlighted = 2
        await wait_for(pilot, lambda: screen.query_one("#unmute").display)
        screen.query_one("#unmute", Button).press()
        await wait_for(pilot, lambda: client.proactive.settings.muted == [])
        listed.highlighted = 1
        await wait_for(pilot, lambda: screen.query_one("#briefing-settings").display)
        screen.query_one("#switch-nightly", Switch).value = False
        await wait_for(pilot, lambda: not client.proactive.settings.nightly)
        times = screen.query_one("#briefing-time", Input)
        times.value = "07:15"
        await times.action_submit()
        await wait_for(pilot, lambda: client.proactive.settings.briefing_time == "07:15")
        screen.query_one("#brief", Button).press()
        await wait_for(pilot, lambda: client.proactive.runs == ["briefing"] and screen.query_one("#brief").disabled)
