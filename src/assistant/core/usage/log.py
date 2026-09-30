"""The tool_calls table and the usage report."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    tool TEXT NOT NULL,
    skill TEXT,
    thread_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tool_calls_at ON tool_calls (at);
"""


@dataclass(frozen=True)
class ToolCall:
    tool: str
    skill: str | None
    thread_id: str
    channel: str
    duration_ms: int
    status: str  # ok | error | denied


@dataclass
class ToolUsage:
    name: str
    calls: int
    errors: int
    denied: int
    avg_ms: int
    last_used: str


@dataclass
class UsageReport:
    days: int
    tools: list[ToolUsage]
    skills: list[ToolUsage]


class UsageLog:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def setup(self) -> None:
        await self._conn.executescript(_SCHEMA)

    async def record(self, call: ToolCall) -> None:
        await self._conn.execute(
            "INSERT INTO tool_calls (at, tool, skill, thread_id, channel, duration_ms, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(UTC).isoformat(),
                call.tool,
                call.skill,
                call.thread_id,
                call.channel,
                call.duration_ms,
                call.status,
            ),
        )

    async def report(self, days: int) -> UsageReport:
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        tools = await self._summary("tool", "at >= ?", since)
        skills = await self._summary("skill", "at >= ? AND skill IS NOT NULL", since)
        return UsageReport(days, tools, skills)

    async def _summary(self, column: str, where: str, since: str) -> list[ToolUsage]:
        query = f"""
            SELECT {column}, COUNT(*), SUM(status = 'error'), SUM(status = 'denied'), AVG(duration_ms), MAX(at)
            FROM tool_calls WHERE {where} GROUP BY {column} ORDER BY COUNT(*) DESC, {column}
        """
        async with self._conn.execute(query, (since,)) as cursor:
            rows = await cursor.fetchall()
        return [
            ToolUsage(name, calls, errors, denied, round(avg), last) for name, calls, errors, denied, avg, last in rows
        ]
