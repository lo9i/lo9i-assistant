"""The /notifications screen: one line per notification, cut to the list's width, and the whole of the one picked
below the list."""

from dataclasses import replace

from textual.widgets import Static

from assistant_terminal.tui.paged_list import PagedOptionList
from assistant_terminal.tui.screens import NotificationsScreen
from tests.terminal.conftest import wait_for

_LONG = "The final diff waits for you.\nThe judge: " + "it matches the plan, " * 20 + "the end."


async def _open(app, pilot) -> PagedOptionList:
    await pilot.click("#prompt")
    await pilot.press(*"/notifications", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, NotificationsScreen))
    options = app.screen.query_one("#notifications-list", PagedOptionList)
    await wait_for(pilot, lambda: options.option_count == 2)
    return options


async def test_each_notification_is_one_line_cut_to_the_width(app, client):
    client.notifications.items[0] = replace(client.notifications.items[0], text=_LONG)
    async with app.run_test(size=(120, 40)) as pilot:
        options = await _open(app, pilot)
        await pilot.pause()
        first, second = (options.render_line(y).text for y in range(2))
        assert "plan my trip" in first and first.rstrip().endswith("…")
        assert "Job daily-news" in second and "Sent the digest." in second


async def test_the_one_picked_shows_whole_below_the_list(app, client):
    client.notifications.items[0] = replace(client.notifications.items[0], text=_LONG)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(app, pilot)
        detail = app.screen.query_one("#notifications-text", Static)
        await wait_for(pilot, lambda: "the end." in str(detail.render()))
        assert "plan my trip" in str(detail.render())
        await pilot.press("down")
        await wait_for(pilot, lambda: "Sent the digest." in str(detail.render()))
        assert "Job daily-news" in str(detail.render())
