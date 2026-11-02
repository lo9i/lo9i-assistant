"""The About you step in the terminal app: shown at start while the profile has no name, and with /about-you;
then the plugins it suggests, each installed only when picked."""

from textual.widgets import Input, OptionList, RadioSet, SelectionList

from assistant.core.agent import AboutYou, FoundServer, Suggested
from assistant_terminal.tui.screens import AboutYouScreen, RepositoryInstallScreen, SuggestedPluginsScreen
from tests.terminal.conftest import wait_for


async def test_with_no_name_it_opens_at_start_and_saves_the_answers(app, client):
    client.memory.about = AboutYou()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for(pilot, lambda: isinstance(app.screen, AboutYouScreen))
        app.screen.query_one("#save").press()
        await wait_for(pilot, lambda: "Write your name." in str(app.screen.query_one("#about-you-message").source))
        app.screen.query_one("#about-you-name", Input).value = " Ana "
        app.screen.query_one("#about-you-language", Input).value = "Spanish"
        app.screen.query_one("#about-you-length", RadioSet).query("RadioButton").first().value = True
        app.screen.query_one("#about-you-help", SelectionList).select("coding")
        app.screen.query_one("#save").press()
        await wait_for(pilot, lambda: not isinstance(app.screen, AboutYouScreen))
        assert client.memory.about == AboutYou("Ana", "Spanish", "short", ["coding"])


async def test_a_name_means_it_waits_for_the_command_which_shows_the_answers(app, client):
    client.memory.about = AboutYou("Ana", reply_length="detailed", help_with=["media"])
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.2)
        assert not isinstance(app.screen, AboutYouScreen)
        await pilot.click("#prompt")
        await pilot.press(*"/about-you", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, AboutYouScreen))
        await wait_for(pilot, lambda: app.screen.query_one("#about-you-name", Input).value == "Ana")
        assert app.screen.query_one("#about-you-length", RadioSet).pressed_index == 1
        assert app.screen.query_one("#about-you-help", SelectionList).selected == ["media"]
        await pilot.press("escape")
        await wait_for(pilot, lambda: not isinstance(app.screen, AboutYouScreen))
        assert client.memory.about.reply_length == "detailed"


async def test_a_suggested_plugin_goes_to_the_usual_install(app, client):
    hosts = FoundServer("hosts", "Servers reached over SSH", "stdio", [], False)
    client.memory.suggestions = [Suggested("hosts", [hosts], [])]
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/about-you", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, AboutYouScreen))
        await wait_for(pilot, lambda: app.screen.query_one("#about-you-name", Input).value == "Ana")
        app.screen.query_one("#save").press()
        await wait_for(pilot, lambda: isinstance(app.screen, SuggestedPluginsScreen))
        assert "hosts" in str(app.screen.query_one(OptionList).get_option_at_index(0).prompt)
        app.screen.query_one(OptionList).action_select()
        await wait_for(pilot, lambda: isinstance(app.screen, RepositoryInstallScreen))
        await pilot.press("escape")
        await wait_for(pilot, lambda: isinstance(app.screen, SuggestedPluginsScreen))
        app.screen.query_one("#done").press()
        await wait_for(pilot, lambda: not isinstance(app.screen, SuggestedPluginsScreen))
        assert client.repositories.installed == []
