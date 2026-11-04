"""The Alerts page, as the web app's: what keeps failing, needs signing in again or the health check found, each listed
by when it last happened with the whole of it beside the list, counted in the sidebar; Open goes to its skill, server
or cause, picked, and Dismiss and Dismiss all take them off."""

from textual.widgets import Button, Markdown, OptionList

from assistant.core.agent import Alert
from assistant_terminal.tui.screens import AlertsScreen, ConfirmScreen, DoctorScreen, SkillsScreen
from assistant_terminal.tui.sidebar import Sidebar
from tests.terminal.conftest import wait_for

_AT = "2030-01-01T09:00:00+00:00"


def _alerts(client) -> None:
    client.alerts.items = [
        Alert("skill", "weekly-review", 3, "exit code 1", _AT),
        Alert("doctor", "c2", 4, "", _AT, kind="growing", title="Poll failed"),
    ]


async def _open(app, pilot) -> AlertsScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/alerts", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, AlertsScreen))
    screen = app.screen
    assert isinstance(screen, AlertsScreen)
    await wait_for(pilot, lambda: screen.query_one("#alerts-list", OptionList).option_count == 2)
    return screen


async def test_each_alert_is_listed_by_when_and_shown_whole_and_counted(app, client):
    _alerts(client)
    async with app.run_test(size=(120, 40)) as pilot:
        sidebar = app.screen.query_one(Sidebar)
        await wait_for(pilot, lambda: any(str(sidebar.get_option(key).prompt) == "! Alerts  2" for key in ["alerts"]))
        screen = await _open(app, pilot)
        listed = screen.query_one("#alerts-list", OptionList)
        assert str(listed.get_option_at_index(0).prompt) == "Tue 01 Jan 09:00"
        body = screen.query_one("#alerts-body", Markdown)
        await wait_for(pilot, lambda: "weekly-review" in body.source and "Failed 3 times in a row." in body.source)
        await pilot.press("down")
        await wait_for(pilot, lambda: "Poll failed" in body.source and "Growing, 4 times" in body.source)


async def test_open_goes_to_its_skill_or_cause_picked(app, client):
    _alerts(client)
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(app, pilot)
        screen.query_one("#open", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, SkillsScreen))
        skills = app.screen.query_one("#skills-list", OptionList)
        await wait_for(
            pilot, lambda: skills.highlighted_option is not None and skills.highlighted_option.id == "weekly-review"
        )
        await pilot.press("escape")  # back to the chat, where /alerts is typed
        await wait_for(pilot, lambda: app.screen is app.screen_stack[0])
        screen = await _open(app, pilot)
        await pilot.press("down")
        screen.query_one("#open", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, DoctorScreen))
        causes = app.screen.query_one("#doctor-list", OptionList)
        await wait_for(pilot, lambda: causes.highlighted_option is not None and causes.highlighted_option.id == "c2")


async def test_dismiss_takes_one_off_and_dismiss_all_asks_first(app, client):
    _alerts(client)
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(app, pilot)
        screen.query_one("#dismiss", Button).press()
        await wait_for(pilot, lambda: [a.name for a in client.alerts.items] == ["c2"])
        screen.query_one("#dismiss-all", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: client.alerts.items == [] and screen.query_one("#alerts").has_class("empty"))
