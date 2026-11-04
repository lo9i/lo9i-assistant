"""The /notifications screen, laid out as /conversations: each listed by what it's about over when it came, and the
whole of the one picked beside the list."""

from dataclasses import replace

from textual.widgets import Markdown

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


async def test_each_notification_is_listed_by_what_its_about_over_when_it_came(app, client):
    client.notifications.items[0] = replace(client.notifications.items[0], text=_LONG)
    async with app.run_test(size=(120, 40)) as pilot:
        options = await _open(app, pilot)
        await pilot.pause()
        lines = [options.render_line(y).text.strip() for y in range(4)]
        assert "plan my trip" in lines[0] and "the end." not in " ".join(lines)
        assert any("Job daily-news" in line for line in lines[1:])
        detail = app.screen.query_one("#notifications-detail")
        assert detail.region.x > options.region.right  # beside the list, not below it


async def test_the_one_picked_shows_whole_beside_the_list(app, client):
    client.notifications.items[0] = replace(client.notifications.items[0], text=_LONG)
    async with app.run_test(size=(120, 40)) as pilot:
        await _open(app, pilot)
        body = app.screen.query_one("#notifications-body", Markdown)
        await wait_for(pilot, lambda: "the end." in body.source)
        assert "plan my trip" in body.source
        await pilot.press("down")
        await wait_for(pilot, lambda: "Sent the digest." in body.source)
        assert "Job daily-news" in body.source
