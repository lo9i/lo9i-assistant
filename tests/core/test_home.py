"""Home: each section built by the worker model from its plugins' read-only tools, answered in one format and
validated, kept between refreshes and refreshed by the daemon at the start of the day and while a client shows it;
a section without its plugin, or that fails, says so without stopping the others. The plugin runs in-process."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from mcp import Client
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from assistant.core.agent import AssistantService, HomeItem, HomeSection, HomeSectionsError, McpServer
from assistant.core.config import settings
from assistant.core.home import results
from assistant.core.home.builder import LIMIT_REACHED, MAX_STEPS
from assistant.core.home.clock import within
from assistant.core.home.model import SectionContent
from assistant.core.home.refresh import FRESH_MINUTES
from assistant.core.mcp import hub as hub_module
from assistant.core.mcp import servers

LIST = "mcp__calendar__list_events"
CREATE = "mcp__calendar__create_event"


def _calendar(created: list[str]) -> MCPServer:
    server = MCPServer("calendar")

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def list_events() -> str:
        """Today's events."""
        return "Standup at 09:00"

    @server.tool()
    def create_event(title: str) -> str:
        """Add an event."""
        created.append(title)
        return f"created {title}"

    return server


@pytest.fixture
def created() -> list[str]:
    return []


@pytest.fixture
async def service(script, digests, summaries, titles, formats, created, monkeypatch) -> AsyncIterator[AssistantService]:
    """The service with its MCP hub running; every server is the in-process calendar."""
    fake = _calendar(created)
    monkeypatch.setattr(
        hub_module,
        "open_client",
        lambda server, handler, auth, extensions: Client(fake, message_handler=handler, extensions=extensions),
    )
    async with AssistantService.open() as svc:
        stop = asyncio.Event()
        task = asyncio.create_task(svc.mcp.run(stop))
        yield svc
        stop.set()
        await task


async def _install_calendar(service: AssistantService, **fields: Any) -> None:
    await servers.save(service.store, McpServer(name="calendar", command="calendar-mcp", **fields))
    await service.mcp.reload()
    for _ in range(100):
        if service.mcp.state("calendar")[0] == "connected":
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("the calendar never connected")


async def _only(service: AssistantService, *titles: str) -> None:
    """Home with these sections, each reading the calendar, built once."""
    sections = [
        HomeSection(id=t.lower(), title=t, prompt=f"{t}: today's events.", plugins=["calendar"]) for t in titles
    ]
    await service.save_home_sections("owner", sections)
    await service.home_refresh.wait("owner")


async def _refreshed(service: AssistantService, force: bool = True):
    await service.refresh_home("owner", force)
    await service.home_refresh.wait("owner")
    return await service.home("owner")


def _bound_names(tools: list[Any]) -> set[str]:
    return {t["function"]["name"] for t in tools}


async def test_home_starts_with_the_built_in_sections_not_built_yet(service):
    page = await service.home("owner")
    assert [c.section.title for c in page.cards] == ["Calendario", "Watchlist", "Gastos"]
    assert [c.section.plugins for c in page.cards] == [["calendar"], ["watchlist"], ["expenses"]]
    assert all(c.section.prompt and c.result is None for c in page.cards)
    assert page.updated_at == "" and not page.refreshing


async def test_a_section_is_built_from_its_plugins_read_only_tools(service, script, formats):
    await _install_calendar(service)
    script.call(LIST).reply("Standup, today 09:00.")
    formats.answers.append(SectionContent(items=[HomeItem(title="Standup", date="2026-10-22", time="09:00")]))
    await _only(service, "Agenda")
    assert _bound_names(script.bound[0]) == {LIST}
    assert [m.text for m in script.requests[1] if isinstance(m, ToolMessage)] == ["Standup at 09:00"]
    assert "What was found:\nStandup, today 09:00." in formats.requests[0][-1].text
    result = (await service.home("owner")).cards[0].result
    assert result is not None and result.status == "ok" and result.title == "Agenda"
    assert result.items == [HomeItem(title="Standup", date="2026-10-22", time="09:00")]


async def test_a_tool_that_can_change_things_never_runs(service, script, created):
    await _install_calendar(service, trusted=True)
    script.call(CREATE, title="Party").reply("Couldn't.")
    await _only(service, "Agenda")
    assert created == []
    refused = [m.text for m in script.requests[1] if isinstance(m, ToolMessage)]
    assert refused == [f"{CREATE} isn't available here: only the section's read-only tools are."]


async def test_the_gathering_stops_at_its_step_limit(service, script):
    await _install_calendar(service)
    for _ in range(MAX_STEPS):
        script.call(LIST)
    script.reply("Standup.")
    await _only(service, "Agenda")
    assert [m.text for m in script.requests[MAX_STEPS] if isinstance(m, ToolMessage)][-1] == LIMIT_REACHED
    assert len(script.requests) == MAX_STEPS + 1


async def test_a_section_without_its_plugin_says_so_without_calling_the_model(service, script):
    await _only(service, "Agenda")
    result = (await service.home("owner")).cards[0].result
    assert result is not None and result.status == "unavailable"
    assert result.error == "Needs the calendar plugin: install it or turn it on in Plugins."
    assert script.requests == []


async def test_a_failing_section_keeps_its_items_and_the_others_are_built(service, formats):
    await _install_calendar(service)
    formats.answers.extend([SectionContent(items=[HomeItem(title="Standup")])] * 2)
    await _only(service, "Agenda", "Work")
    formats.failing = {"Agenda"}
    formats.answers.append(SectionContent(items=[HomeItem(title="Review")]))
    cards = {c.section.title: c.result for c in (await _refreshed(service)).cards}
    agenda, work = cards["Agenda"], cards["Work"]
    assert agenda is not None and agenda.status == "failed" and agenda.error == "the model is down"
    assert agenda.items == [HomeItem(title="Standup")]
    assert work is not None and work.status == "ok" and work.items == [HomeItem(title="Review")]


async def test_an_answer_that_doesnt_fit_the_format_fails_the_section(service, formats):
    await _install_calendar(service)
    formats.answers.append({"items": [{"title": "Standup", "time": "9am"}]})
    await _only(service, "Agenda")
    result = (await service.home("owner")).cards[0].result
    assert result is not None and result.status == "failed" and "isn't a time as HH:MM" in result.error


async def test_a_refresh_within_ten_minutes_of_the_last_does_nothing_unless_forced(service, formats):
    await _install_calendar(service)
    await _only(service, "Agenda")
    page = await _refreshed(service)
    assert page.updated_at and len(formats.requests) == 2
    await _refreshed(service, force=False)
    assert len(formats.requests) == 2
    await results.mark_refreshed(service.store, "owner", datetime.now(UTC) - timedelta(minutes=11))
    await _refreshed(service, force=False)
    assert len(formats.requests) == 3


async def test_a_refresh_says_its_running_until_every_section_is_saved(service, formats):
    await _install_calendar(service)
    await _only(service, "Agenda")
    formats.gate = asyncio.Event()
    formats.answers.append(SectionContent(items=[HomeItem(title="Standup")]))
    assert (await service.refresh_home("owner", force=True)).refreshing
    formats.gate.set()
    await service.home_refresh.wait("owner")
    page = await service.home("owner")
    assert not page.refreshing
    assert page.cards[0].result is not None and page.cards[0].result.items == [HomeItem(title="Standup")]


async def test_saving_builds_new_and_changed_sections_and_forgets_removed_ones(service, formats):
    await _install_calendar(service)
    await _only(service, "Agenda", "Work")
    assert len(formats.requests) == 2
    agenda = HomeSection(id="agenda", title="My day", prompt="Agenda: today's events.", plugins=["calendar"])
    trips = HomeSection(title="Trips", prompt="Flights this month.", plugins=["calendar"])
    await service.save_home_sections("owner", [agenda, trips])
    await service.home_refresh.wait("owner")
    assert len(formats.requests) == 3 and "Section: Trips\n" in formats.requests[-1][-1].text
    page = await service.home("owner")
    assert [c.section.title for c in page.cards] == ["My day", "Trips"] and page.cards[1].section.id
    assert set(await results.load(service.store, "owner")) == {"agenda", page.cards[1].section.id}


@pytest.mark.parametrize(
    ("sections", "error"),
    [
        ([HomeSection(title=" ", prompt="x")], "Every section needs a title."),
        ([HomeSection(title="A", prompt=" ")], "Say what A shows."),
        ([HomeSection(id="a", title="A", prompt="x"), HomeSection(id="a", title="B", prompt="y")], "same id"),
    ],
)
async def test_sections_that_cant_be_saved_are_refused(service, sections, error):
    with pytest.raises(HomeSectionsError, match=error):
        await service.save_home_sections("owner", sections)


async def test_resetting_goes_back_to_the_built_in_sections(service):
    await _only(service, "Agenda")
    page = await service.reset_home_sections("owner")
    await service.home_refresh.wait("owner")
    assert [c.section.title for c in page.cards] == ["Calendario", "Watchlist", "Gastos"]
    assert "agenda" not in await results.load(service.store, "owner")


async def test_a_section_links_to_its_plugins_page(service):
    await _install_calendar(service, page_command="calendar-web")
    await _only(service, "Agenda")
    result = (await service.home("owner")).cards[0].result
    assert result is not None and result.page == "calendar"


# A fixed afternoon, so the day boundaries don't depend on when the tests run.
NOW = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)


async def _tick(service: AssistantService, refreshed: datetime) -> None:
    """A tick of the daemon's schedule at NOW, after a refresh at `refreshed`."""
    await results.mark_refreshed(service.store, "owner", refreshed)
    await service.home_schedule.tick(NOW)
    await service.home_refresh.wait("owner")


async def test_home_is_refreshed_on_the_first_tick_of_the_day(service, formats):
    await _install_calendar(service)
    await _only(service, "Agenda")
    await _tick(service, NOW - timedelta(hours=16))
    assert len(formats.requests) == 2
    await _tick(service, NOW - timedelta(hours=2))
    assert len(formats.requests) == 2  # nobody watching: once a day is enough


async def test_home_is_refreshed_every_half_hour_while_a_client_shows_it(service, formats):
    await _install_calendar(service)
    await _only(service, "Agenda")
    service.watch_home("tab")
    await _tick(service, NOW - timedelta(minutes=20))
    assert len(formats.requests) == 1
    await _tick(service, NOW - timedelta(minutes=31))
    assert len(formats.requests) == 2
    service.unwatch_home("tab")
    await _tick(service, NOW - timedelta(minutes=31))
    assert len(formats.requests) == 2


def test_a_refresh_from_before_midnight_isnt_current_after_it(monkeypatch):
    monkeypatch.setattr(settings, "timezone", "America/Argentina/Buenos_Aires")
    before_midnight = datetime(2026, 10, 22, 2, 55, tzinfo=UTC)  # 23:55 there
    assert within(before_midnight, before_midnight + timedelta(minutes=4), FRESH_MINUTES)
    assert not within(before_midnight, before_midnight + timedelta(minutes=6), FRESH_MINUTES)
    assert not within(None, before_midnight, FRESH_MINUTES)
