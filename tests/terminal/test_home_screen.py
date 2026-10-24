"""/home: Home's sections with what the assistant last built, refreshed, added, edited, moved and removed."""

from datetime import date, datetime, timedelta, timezone

from textual.widgets import Button, Input, Markdown, SelectionList, TextArea

from assistant.core.agent import HomeCard, HomeItem, HomeSection, SectionResult
from assistant_terminal.home_text import describe, item_when, updated
from assistant_terminal.tui.screens import ConfirmScreen, HomeScreen
from assistant_terminal.tui.screens.home_section import HomeSectionScreen
from tests.terminal.conftest import wait_for

TODAY = date(2026, 10, 24)


def test_when_an_item_is_reads_as_the_web_app_says_it():
    assert item_when(HomeItem(title="a", time="09:00"), TODAY) == "09:00"
    assert item_when(HomeItem(title="a", date="2026-10-24"), TODAY) == "Today"
    assert item_when(HomeItem(title="a", date="2026-10-25", time="21:00"), TODAY) == "Tomorrow 21:00"
    assert item_when(HomeItem(title="a", date="2026-10-30"), TODAY) == "Fri 30 Oct"
    assert item_when(HomeItem(title="a"), TODAY) == ""


def test_a_section_says_what_it_found_or_why_it_has_nothing():
    section = HomeSection(id="c", title="Calendar", prompt="x")
    assert describe(HomeCard(section=section), TODAY) == "Not built yet: Refresh builds it."
    failed = SectionResult(
        section_id="c", title="Calendar", status="failed", error="the calendar didn't answer",
        items=[HomeItem(title="Dentist", time="09:30")], at="2026-10-24T08:00:00+00:00",
    )  # fmt: skip
    text = describe(HomeCard(section=section, result=failed), TODAY)
    assert "Couldn't build it:** the calendar didn't answer" in text and "- **Dentist** · 09:30" in text
    empty = SectionResult(section_id="c", title="Calendar", status="ok", note="Nothing today.", at="x")
    assert describe(HomeCard(section=section, result=empty), TODAY) == "_Nothing today._"


def test_when_home_was_updated():
    now = datetime(2026, 10, 24, 12, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert updated("2026-10-24T13:32:00+00:00", now) == "Updated 10:32"
    assert updated("2026-10-21T21:05:00+00:00", now) == "Updated Wed 21 Oct 18:05"
    assert updated("", now) == ""


async def test_home_shows_its_sections_and_keeps_current_while_its_open(app, client):
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/home", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#home-body", Markdown).source

        await wait_for(pilot, lambda: "**Dentist** · Av. Corrientes 1234 · 09:30" in body())
        assert client.home.watching and client.home.refreshes == [False]
        screen.query_one("#refresh", Button).press()
        await wait_for(pilot, lambda: client.home.refreshes == [False, True])
        screen.dismiss()
        await wait_for(pilot, lambda: not client.home.watching)


async def test_a_section_is_added_with_its_plugins_and_a_refusal_keeps_it_open(app, client):
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/home", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        home = app.screen
        home.query_one("#add", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, HomeSectionScreen))
        editor = app.screen
        editor.query_one("#home-section-name", Input).value = "Notes"
        editor.query_one("#home-section-prompt", TextArea).text = "My latest notes."
        editor.query_one("#home-section-plugins", SelectionList).select("notes")
        client.home.refusal = "Two sections can't have the same title."
        editor.query_one("#save", Button).press()
        message = editor.query_one("#home-section-message", Markdown)
        await wait_for(pilot, lambda: "same title" in message.source)
        client.home.refusal = ""
        editor.query_one("#save", Button).press()
        await wait_for(pilot, lambda: app.screen is home)
        assert [(s.title, s.plugins) for s in client.home.sections] == [
            ("Calendar", ["calendar"]),
            ("Notes", ["notes"]),
        ]
        await wait_for(pilot, lambda: "Not built yet" in home.query_one("#home-body", Markdown).source)


async def test_sections_are_moved_removed_and_reset(app, client):
    client.home.sections.append(HomeSection(id="notes", title="Notes", prompt="x"))
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/home", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, HomeScreen))
        home = app.screen
        await pilot.pause()
        home.query_one("#down", Button).press()
        await wait_for(pilot, lambda: [s.id for s in client.home.sections] == ["notes", "calendar"])
        home.query_one("#remove", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: [s.id for s in client.home.sections] == ["notes"])
        home.query_one("#reset", Button).press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: [s.id for s in client.home.sections] == ["calendar"])
