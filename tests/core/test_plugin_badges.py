"""A plugin's count beside its page in the sidebar (core/mcp/badges.py): the `badge:` section, its answer read as
structured content or text, a plugin that fails or is slow left out, and when the user's day ends."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from langgraph.store.memory import InMemoryStore
from mcp.types import CallToolResult, TextContent

from lo9i.core.mcp import badges, servers
from lo9i.core.mcp.badges import Badges, PluginBadge
from lo9i.core.mcp.servers import McpServer

LEDGER = McpServer(name="ledger", command="ledger-mcp", badge_tool="due_today")
# 20:00 on Nov 4 in Buenos Aires (UTC-3).
NOW = datetime(2026, 11, 4, 23, 0, tzinfo=UTC)


def _text(value: str, error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=value)], is_error=error)


class _Calls:
    def __init__(self, results: dict[str, CallToolResult | float]) -> None:
        """A plugin's result, or how long it takes never to answer."""
        self.results = results
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> CallToolResult:
        self.calls.append((server, tool, arguments))
        result = self.results[server]
        if isinstance(result, CallToolResult):
            return result
        await asyncio.sleep(result)
        raise AssertionError("not reached")


@pytest.fixture(autouse=True)
def buenos_aires(monkeypatch):
    monkeypatch.setattr("lo9i.core.config.settings.timezone", "America/Argentina/Buenos_Aires")


def test_the_section_names_a_tool():
    assert badges.parse(None) == {}
    assert badges.parse({"tool": " due_today "}) == {"badge_tool": "due_today"}
    with pytest.raises(ValueError):
        badges.parse({"command": "x"})


def test_the_agent_never_gets_the_tool_and_the_apps_dont_list_it():
    assert not LEDGER.selects("due_today") and LEDGER.selects("list_bills")
    assert LEDGER.only_lo9i_calls("due_today") and not LEDGER.only_lo9i_calls("list_bills")


def test_a_call_that_may_change_things_has_it_counted_again():
    assert badges.recounts_after(LEDGER, "pay_bill", read_only=False)
    assert not badges.recounts_after(LEDGER, "list_bills", read_only=True)
    assert not badges.recounts_after(LEDGER, "due_today", read_only=False)
    assert not badges.recounts_after(McpServer(name="notes", command="x"), "add_note", read_only=False)


def test_the_day_ends_at_midnight_in_the_users_time_zone():
    assert badges.next_day_in(NOW) == 4 * 3600 + 1


async def test_each_plugin_counts_on_the_users_day_and_only_counts_above_zero_show():
    store = InMemoryStore()
    for server in [
        LEDGER,
        McpServer(name="calendar", command="calendar-mcp", badge_tool="badge"),
        McpServer(name="quiet", command="quiet-mcp", badge_tool="badge"),
        McpServer(name="off", command="off-mcp", badge_tool="badge", enabled=False),
        McpServer(name="notes", command="notes-mcp"),
    ]:
        await servers.save(store, server)
    calls = _Calls(
        {
            "ledger": CallToolResult(content=[], structured_content={"count": 2, "label": " 2 bills due today "}),
            "calendar": _text(json.dumps({"count": 1})),
            "quiet": _text(json.dumps({"count": 0, "label": "nothing"})),
        }
    )
    counted = await Badges(store, calls).every("es", NOW)
    assert sorted(calls.calls) == [
        ("calendar", "badge", {"day": "2026-11-04", "language": "es"}),
        ("ledger", "due_today", {"day": "2026-11-04", "language": "es"}),
        ("quiet", "badge", {"day": "2026-11-04", "language": "es"}),
    ]
    assert sorted(counted.badges, key=lambda b: b.name) == [
        PluginBadge("calendar", 1),
        PluginBadge("ledger", 2, "2 bills due today"),
    ]
    assert counted.next_day_in == 4 * 3600 + 1


@pytest.mark.parametrize(
    "result",
    [
        _text("the database is locked", error=True),
        _text("not json"),
        _text(json.dumps({"count": -1})),
        0.5,
    ],
)
async def test_a_plugin_that_fails_or_is_slow_shows_no_count(result, monkeypatch):
    monkeypatch.setattr(badges, "BADGE_SECONDS", 0.05)
    store = InMemoryStore()
    await servers.save(store, LEDGER)
    assert (await Badges(store, _Calls({"ledger": result})).every("en", NOW)).badges == []
