"""A plugin's count beside its page in the web app's sidebar: `badge:` in its server.yaml names a read-only tool of its
MCP server that counts what the user should see to now (the bills due today, unpaid). lo9i calls it itself, never
through the model, when the sidebar asks (`GET /mcp/badges`); no count, or 0, shows nothing. The agent never gets the
tool: its other tools read the same things. What a plugin writes is in docs/plugin-badges.md.

    badge:
      tool: badge                  # called with {"day": "2026-11-04", "language": "en"}: the user's day, in their time
                                   # zone, and the language the apps show (en or es), to write its label in

It answers `{"count": 2, "label": "2 bills due today"}` (as its structured result, or as its text). The sidebar asks
again when the event `badges` says a count may have changed: a call of one of the plugin's tools that doesn't only
read (the assistant paid a bill), a change made on its page (anything but GET and HEAD through daemon/pages.py), and
when the user's day ends (`next_day_in`)."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from langgraph.store.base import BaseStore
from mcp.types import CallToolResult
from pydantic import BaseModel, NonNegativeInt

from lo9i.core.config import settings
from lo9i.core.i18n import said
from lo9i.core.mcp import servers
from lo9i.core.mcp.servers import McpServer

logger = logging.getLogger(__name__)

_PARTS = said("its badge section must name a tool")
# The sidebar waits for the counts; a plugin slower than this shows none.
BADGE_SECONDS = 10
# What tells the apps a count may have changed.
EVENT = "badges"


class _Answer(BaseModel):
    count: NonNegativeInt = 0
    label: str = ""


@dataclass
class PluginBadge:
    name: str
    count: int
    # What the count is, in the apps' language, for the tooltip and screen readers; "" when the plugin gave none.
    label: str = ""


@dataclass
class PluginBadges:
    # Only the plugins with something to count.
    badges: list[PluginBadge] = field(default_factory=list)
    # Seconds until the user's day ends, when counts of the day (due today) change with nothing else happening.
    next_day_in: int = 0


class ToolCalls(Protocol):
    """Calls a plugin's tool directly (core/mcp/hub.py)."""

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> CallToolResult: ...


def parse(value: object) -> dict[str, Any]:
    """The `badge:` section as the server's field; none without one. Raises ValueError for one that can't be used."""
    if value is None:
        return {}
    tool = str(value.get("tool") or "").strip() if isinstance(value, dict) else ""
    if not tool:
        raise ValueError(_PARTS)
    return {"badge_tool": tool}


def recounts_after(server: McpServer, tool: str, read_only: bool) -> bool:
    """Whether a call of `tool` may have changed what the server's badge counts: one that doesn't only read, never the
    badge's own, which the recount calls."""
    return bool(server.badge_tool) and tool != server.badge_tool and not read_only


def next_day_in(now: datetime) -> int:
    """Seconds from `now` to the start of the user's next day, in their time zone."""
    zone = ZoneInfo(settings.timezone)
    tomorrow = datetime.combine(now.astimezone(zone).date() + timedelta(days=1), time(), zone)
    return max(1, int((tomorrow.astimezone(UTC) - now.astimezone(UTC)).total_seconds()) + 1)


class Badges:
    """Every plugin's count, for the web app's sidebar."""

    def __init__(self, store: BaseStore, calls: ToolCalls) -> None:
        self._store = store
        self._calls = calls

    async def every(self, language: str, now: datetime | None = None) -> PluginBadges:
        """The counts above 0, in the order the plugins are listed. A plugin that fails or is slow is left out, and
        logged."""
        now = now or datetime.now(UTC)
        day = now.astimezone(ZoneInfo(settings.timezone)).date().isoformat()
        counting = [s for s in await servers.load_all(self._store) if s.enabled and s.badge_tool]
        found = await asyncio.gather(*(self._badge(s, day, language) for s in counting))
        return PluginBadges([b for b in found if b is not None and b.count], next_day_in(now))

    async def _badge(self, server: McpServer, day: str, language: str) -> PluginBadge | None:
        try:
            async with asyncio.timeout(BADGE_SECONDS):
                result = await self._calls.call(server.name, server.badge_tool, {"day": day, "language": language})
            if result.is_error:
                raise ValueError(_text(result))
            answer = _Answer.model_validate(_value(result))
        except Exception as e:
            logger.info("%s couldn't count its badge: %s", server.name, e)
            return None
        return PluginBadge(server.name, answer.count, answer.label.strip())


def _value(result: CallToolResult) -> Any:
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(_text(result))


def _text(result: CallToolResult) -> str:
    return "\n".join(block.text for block in result.content if block.type == "text")
