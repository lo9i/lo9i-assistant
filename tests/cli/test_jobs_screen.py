from textual.widgets import Button, Markdown, OptionList

from assistant.gateways.cli.tui.screens import ConfirmScreen, JobsScreen
from tests.cli.conftest import wait_for


async def _open(pilot, app) -> JobsScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/jobs", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, JobsScreen))
    return app.screen


async def test_lists_shows_pauses_and_deletes(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app)

        def body() -> str:
            return screen.query_one("#job-body", Markdown).source

        await wait_for(pilot, lambda: "Run the skill news-digest" in body())
        assert "**ok**: Sent the digest." in body() and "At 09:00, every day (`0 9 * * *`, UTC)" in body()
        options = screen.query_one("#jobs-list", OptionList)
        assert [str(options.get_option_at_index(i).prompt) for i in range(2)] == ["daily-news", "stretch"]
        toggle = screen.query_one("#toggle", Button)
        toggle.press()
        await wait_for(pilot, lambda: not client.jobs.items["daily-news"].enabled and "paused" in body())
        assert str(toggle.label) == "Resume"
        screen.query_one("#delete", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("enter")  # Cancel has the focus
        await wait_for(pilot, lambda: app.screen is screen)
        assert list(client.jobs.items) == ["daily-news", "stretch"]
        screen.query_one("#delete", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: list(client.jobs.items) == ["stretch"] and "once at" in body())


async def test_refreshes_when_a_job_changes(app, client):
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await _open(pilot, app)
        client.jobs.items.clear()
        await client.bus.put(("jobs", {}))
        await wait_for(pilot, lambda: screen.query_one("#jobs").has_class("empty"))
        await pilot.press("enter")  # Close is the only action left
        await wait_for(pilot, lambda: not isinstance(app.screen, JobsScreen))


def test_schedules_read_as_words():
    from assistant.gateways.cli.jobs_text import frequency

    assert frequency("0 9 * * *") == "At 09:00, every day"
    assert frequency("*/15 * * * *") == "Every 15 minutes"
    assert frequency("30 8 * * 1-5") == "At 08:30, Monday through Friday"
