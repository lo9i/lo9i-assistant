"""A plugin's list for the day (core/mcp/today.py): the `today:` section, its answer read as structured content or text,
and an answer lo9i can't read or an error said as such."""

import json
from typing import Any

import pytest
from mcp.types import CallToolResult, TextContent

from lo9i.core.mcp import today
from lo9i.core.mcp.servers import McpServer
from lo9i.core.mcp.today import MAX_ITEMS, TodayListError

PLANNER = McpServer(name="planner", command="planner-mcp", today_tool="today")


class _Calls:
    def __init__(self, result: CallToolResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> CallToolResult:
        self.calls.append((server, tool, arguments))
        return self.result


def _text(value: str, error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=value)], is_error=error)


def test_the_section_names_a_tool():
    assert today.parse(None) == {}
    assert today.parse({"tool": " today "}) == {"today_tool": "today"}
    with pytest.raises(ValueError):
        today.parse({"command": "x"})


def test_the_agent_never_gets_the_tool_and_the_apps_dont_list_it():
    assert not PLANNER.selects("today") and PLANNER.selects("list_events")
    assert PLANNER.only_lo9i_calls("today") and not PLANNER.only_lo9i_calls("list_events")


async def test_its_answer_is_read_from_its_structured_result_or_its_text():
    structured = CallToolResult(content=[], structured_content={"heading": "Bills", "items": [{"title": "Gas"}]})
    calls = _Calls(structured)
    listed = await today.read(calls, PLANNER, "2026-11-03", "es")
    assert calls.calls == [("planner", "today", {"day": "2026-11-03", "language": "es"})]
    assert (listed.heading, [i.title for i in listed.items]) == ("Bills", ["Gas"])
    many = [{"title": str(n)} for n in range(MAX_ITEMS + 5)]
    assert len((await today.read(_Calls(_text(json.dumps({"items": many}))), PLANNER, "d", "en")).items) == MAX_ITEMS


@pytest.mark.parametrize(
    ("result", "said"),
    [
        (_text("the database is locked", error=True), "planner couldn't list its day: the database is locked"),
        (_text("not json"), "planner listed its day in a form lo9i can't read"),
        (_text(json.dumps({"items": [{"title": "x", "date": "Thursday"}]})), "can't read"),
    ],
)
async def test_an_error_or_an_answer_it_cant_read_says_so(result: CallToolResult, said: str):
    with pytest.raises(TodayListError, match=said):
        await today.read(_Calls(result), PLANNER, "2026-11-03", "en")
