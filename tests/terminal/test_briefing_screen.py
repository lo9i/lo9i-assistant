"""/briefing, Settings' Briefing and reviews section: each feature on or off, the times, and a kind muted suggested
again."""

from textual.widgets import Button, Input, OptionList, Switch

from lo9i_terminal.tui.screens import BriefingSection
from tests.terminal.conftest import wait_for, wait_for_section


async def test_the_settings_change_and_a_muted_kind_is_suggested_again(app, client):
    client.proactive.settings = client.proactive.settings.model_copy(update={"muted": ["bill due"]})
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/briefing", "enter")
        screen = await wait_for_section(pilot, app, BriefingSection)
        listed = screen.query_one("#briefing-list", OptionList)
        await wait_for(pilot, lambda: listed.option_count == 2 and screen.query_one("#briefing-settings").display)
        screen.query_one("#switch-nightly", Switch).value = False
        await wait_for(pilot, lambda: not client.proactive.settings.nightly)
        times = screen.query_one("#briefing-time", Input)
        times.value = "07:15"
        await times.action_submit()
        await wait_for(pilot, lambda: client.proactive.settings.briefing_time == "07:15")
        listed.highlighted = 1
        await wait_for(pilot, lambda: screen.query_one("#unmute").display)
        screen.query_one("#unmute", Button).press()
        await wait_for(pilot, lambda: client.proactive.settings.muted == [] and listed.option_count == 1)
