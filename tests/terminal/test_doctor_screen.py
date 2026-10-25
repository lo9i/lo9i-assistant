"""/doctor: the latest health check's overview with its starting context, each cause it found, checking now, and
marking a cause as known noise and back. A health check's notification opens it."""

from datetime import datetime

from textual.widgets import Button, Markdown, OptionList

from assistant.core.agent import Notification
from assistant_terminal.doctor_text import cause_line, overview, times
from assistant_terminal.tui.screens import DoctorScreen, NotificationsScreen
from tests.terminal.conftest import FakeDoctor, wait_for


def test_a_cause_says_how_it_changed_and_how_often():
    growing, warning = FakeDoctor().report.causes
    assert cause_line(growing) == "[Growing] ConnectionError: refused · 3 times (1 the day before)"
    assert times(warning) == "once"


def test_the_overview_says_what_was_checked_whats_gone_and_the_starting_context():
    text = overview(FakeDoctor().report)
    assert text.startswith("Sat 24 Oct, the whole day, checked Sat 24 Oct 23:59; compared with 2026-10-23.")
    assert "**Gone since 2026-10-23:** KeyError: 'title'" in text
    assert "12.0k of 150.0k tokens, 8%" in text and "- Saved facts: 3.1k (+800.0)" not in text
    assert "- Saved facts: 3.1k (+800)" in text and "- Skills: 900" in text
    assert overview(None).startswith("Not checked yet.")


async def test_the_health_check_shows_its_causes_checks_now_and_marks_noise(app, client):
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/doctor", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, DoctorScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#doctor-body", Markdown).source

        await wait_for(pilot, lambda: "Starting context" in body())
        assert not screen.query_one("#known").display
        screen.query_one("#doctor-list", OptionList).highlighted = 2
        await wait_for(pilot, lambda: "**Poll failed**" in body())
        assert "`assistant.core.channels.telegram`" in body()
        screen.query_one("#known", Button).press()
        await wait_for(pilot, lambda: [k.id for k in client.doctor.known] == ["c2"])
        listed = screen.query_one("#doctor-list", OptionList)
        await wait_for(pilot, lambda: "Known: Poll failed" in str(listed.get_option_at_index(2).prompt))
        listed.highlighted = 2
        await wait_for(pilot, lambda: screen.query_one("#forget").display)
        screen.query_one("#forget", Button).press()
        await wait_for(pilot, lambda: client.doctor.known == [])
        screen.query_one("#check", Button).press()
        await wait_for(pilot, lambda: client.doctor.checks == 1 and screen.query_one("#check", Button).disabled)


async def test_a_health_checks_notification_opens_it(app, client):
    at = datetime.now().astimezone().isoformat()
    client.notifications.items.insert(0, Notification("n0", at, "doctor", "Health check of Sat 24 Oct", "x", False))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/notifications", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, NotificationsScreen))
        await wait_for(pilot, lambda: str(app.screen.query_one("#open", Button).label) == "Open the health check")
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, DoctorScreen))
