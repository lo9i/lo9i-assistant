"""A plugin's list for the day: `today:` in its server.yaml names a read-only tool of its MCP server that lists what
the user should see that day (today's events, bills coming due, invoices to issue), in one format every plugin
shares. lo9i calls it itself, never through the model, so the morning briefing (core/proactive/), the nightly review
and Home's sections (core/home/) show it without a model call. The agent never gets the tool: its other tools read
the same things. What a plugin writes is in docs/today-lists.md.

    today:
      tool: today                  # called with {"day": "2026-11-03", "language": "en"}: the user's day, in their time
                                   # zone, and the language the apps show (en or es), to write its texts in

It answers a JSON object (as its structured result, or as its text): a heading, its items in the order to show them,
each one as Home shows an item plus what needs doing about it, and a note. A daemon from before `today:` installs the
plugin without it, the tool then offered to the agent like any other, so it needs no new format."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from langgraph.store.base import BaseStore
from mcp.types import CallToolResult
from pydantic import BaseModel, Field, ValidationError

from lo9i.core.home.model import HomeItem
from lo9i.core.i18n import message, said
from lo9i.core.mcp import servers
from lo9i.core.mcp.servers import McpServer

logger = logging.getLogger(__name__)

_PARTS = said("its today section must name a tool")
# A list longer than this is cut: it's read on a phone.
MAX_ITEMS = 30


class TodayItem(HomeItem):
    needs: str = Field(
        default="",
        description="What the user has to do about it, in a short sentence that reads on its own (Pay the "
        "electricity bill, due Thu 5); empty when nothing. lo9i keeps it as an open loop.",
    )
    kind: str = Field(
        default="", description="What kind of thing it is, in English (calendar, bill due, invoices to issue)."
    )
    key: str = Field(default="", description="What it's known by across days, so it's kept as an open loop once.")


class TodayList(BaseModel):
    heading: str = ""
    items: list[TodayItem] = []
    note: str = ""


class TodayListError(Exception):
    """The plugin's list couldn't be read. The text says why."""


class ToolCalls(Protocol):
    """Calls a plugin's tool directly (core/mcp/hub.py)."""

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> CallToolResult: ...


def parse(value: object) -> dict[str, Any]:
    """The `today:` section as the server's field; none without one. Raises ValueError for one that can't be used."""
    if value is None:
        return {}
    tool = str(value.get("tool") or "").strip() if isinstance(value, dict) else ""
    if not tool:
        raise ValueError(_PARTS)
    return {"today_tool": tool}


async def read(calls: ToolCalls, server: McpServer, day: str, language: str) -> TodayList:
    """The plugin's list for `day`. Raises TodayListError."""
    try:
        result = await calls.call(server.name, server.today_tool, {"day": day, "language": language})
    except Exception as e:
        raise TodayListError(said("{plugin} couldn't list its day: {error}", plugin=server.name, error=e)) from e
    if result.is_error:
        raise TodayListError(said("{plugin} couldn't list its day: {error}", plugin=server.name, error=_text(result)))
    try:
        listed = TodayList.model_validate(_value(result))
    except (ValueError, ValidationError) as e:
        raise TodayListError(
            said("{plugin} listed its day in a form lo9i can't read: {error}", plugin=server.name, error=e)
        ) from e
    return listed.model_copy(update={"items": listed.items[:MAX_ITEMS]})


def _value(result: CallToolResult) -> Any:
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(_text(result))


def _text(result: CallToolResult) -> str:
    return "\n".join(block.text for block in result.content if block.type == "text")


@dataclass(frozen=True)
class Listed:
    plugin: str
    # None when it couldn't be read.
    today: TodayList | None
    error: str = ""


class TodayLists:
    """Every plugin's list for the day, for the briefing, the nightly review and Home."""

    def __init__(self, store: BaseStore, calls: ToolCalls) -> None:
        self._store = store
        self._calls = calls

    async def plugins(self) -> list[McpServer]:
        """The plugins on that list their day."""
        return [s for s in await servers.load_all(self._store) if s.enabled and s.today_tool]

    async def of(self, plugin: str, day: str, language: str) -> TodayList:
        """Raises TodayListError, also for a plugin that's off or lists nothing."""
        found = next((s for s in await self.plugins() if s.name == plugin), None)
        if found is None:
            raise TodayListError(said("{plugin} doesn't list its day, or is off.", plugin=plugin))
        return await read(self._calls, found, day, language)

    async def every(self, day: str, language: str) -> list[Listed]:
        """Each plugin's list, or why it couldn't be read, in the order the plugins are listed."""
        return [await self._listed(s, day, language) for s in await self.plugins()]

    async def _listed(self, server: McpServer, day: str, language: str) -> Listed:
        try:
            return Listed(server.name, await read(self._calls, server, day, language))
        except TodayListError as e:
            logger.info("%s", e)
            return Listed(server.name, None, message(e))
