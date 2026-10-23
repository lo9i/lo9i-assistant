"""Usage in SQLite: the tool_calls table (every tool call), the model_calls ledger (every model
call, with its tokens) and token_parts (each call's tokens split among the system prompt, history,
the user's message, tools and the reply; core/usage/tokens.py). Reports read them back."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import aiosqlite

from assistant.core.usage import prices
from assistant.core.usage.tokens import Part

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
CREATE INDEX IF NOT EXISTS tool_calls_thread ON tool_calls (thread_id);
CREATE TABLE IF NOT EXISTS model_calls (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    purpose TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    job TEXT,
    skill TEXT,
    input_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_write_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    reasoning_tokens INTEGER NOT NULL,
    estimated INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS model_calls_at ON model_calls (at);
CREATE INDEX IF NOT EXISTS model_calls_thread ON model_calls (thread_id);
CREATE TABLE IF NOT EXISTS token_parts (
    call_id INTEGER NOT NULL REFERENCES model_calls (id),
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS token_parts_call ON token_parts (call_id);
"""

# Conversations and tools listed in a token report, the most tokens first.
_TOP = 15


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


@dataclass(frozen=True)
class ModelCall:
    """One model call's tokens, as the provider reported them. `input_tokens` counts every input
    token, the ones read from or written to the prompt cache included."""

    # reply (the conversation), summary (an epoch's digest), title, check (a model being set up).
    purpose: str
    provider: str
    model: str
    thread_id: str
    channel: str
    job: str | None
    skill: str | None
    input_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    output_tokens: int
    reasoning_tokens: int
    # The provider reported no usage: the counts are a local estimate.
    estimated: bool


@dataclass
class TokenRow:
    """Tokens of one day, model, conversation, tool... `cost` in US dollars, None when no model
    involved has a price (core/usage/prices.py)."""

    name: str
    # What to show for `name` when it isn't readable (a conversation's title).
    label: str = ""
    calls: int = 0
    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = None


@dataclass
class TokenReport:
    days: int
    total: TokenRow
    by_day: list[TokenRow] = field(default_factory=list)
    by_model: list[TokenRow] = field(default_factory=list)
    by_purpose: list[TokenRow] = field(default_factory=list)
    by_channel: list[TokenRow] = field(default_factory=list)
    by_conversation: list[TokenRow] = field(default_factory=list)
    by_job: list[TokenRow] = field(default_factory=list)
    # Calls made while a skill was in use: everything they cost.
    by_skill: list[TokenRow] = field(default_factory=list)
    # The tokens each tool's results and calls took (core/usage/tokens.py); `calls` counts the
    # model calls they were part of. No cost: the cache price that applied isn't known per part.
    by_tool: list[TokenRow] = field(default_factory=list)
    # Calls whose provider reported no usage, counted by estimate.
    estimated_calls: int = 0


@dataclass(frozen=True)
class ThreadUsage:
    """One conversation's model calls, every purpose included (replies, summaries, titles), and its tool
    calls. `input_tokens` counts the cache reads too."""

    model_calls: int = 0
    input_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0


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

    async def record_model_call(self, call: ModelCall, parts: Sequence[Part]) -> None:
        cursor = await self._conn.execute(
            "INSERT INTO model_calls (at, purpose, provider, model, thread_id, channel, job, skill, input_tokens, "
            "cache_read_tokens, cache_write_tokens, output_tokens, reasoning_tokens, estimated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(UTC).isoformat(),
                call.purpose,
                call.provider,
                call.model,
                call.thread_id,
                call.channel,
                call.job,
                call.skill,
                call.input_tokens,
                call.cache_read_tokens,
                call.cache_write_tokens,
                call.output_tokens,
                call.reasoning_tokens,
                int(call.estimated),
            ),
        )
        await self._conn.executemany(
            "INSERT INTO token_parts (call_id, kind, name, input_tokens, output_tokens) VALUES (?, ?, ?, ?, ?)",
            [(cursor.lastrowid, p.kind, p.name, p.input_tokens, p.output_tokens) for p in parts],
        )

    async def token_report(self, days: int) -> TokenReport:
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        by = {
            group: await self._token_rows(column, since)
            for group, column in (
                ("day", "substr(at, 1, 10)"),
                ("model", "model"),
                ("purpose", "purpose"),
                ("channel", "channel"),
                ("conversation", "thread_id"),
                ("job", "job"),
                ("skill", "skill"),
            )
        }
        totals = await self._token_rows("'total'", since)
        return TokenReport(
            days,
            totals[0] if totals else TokenRow("total"),
            by_day=sorted(by["day"], key=lambda r: r.name),
            by_model=by["model"],
            by_purpose=by["purpose"],
            by_channel=[r for r in by["channel"] if r.name],
            by_conversation=[r for r in by["conversation"] if r.name][:_TOP],
            by_job=[r for r in by["job"] if r.name],
            by_skill=[r for r in by["skill"] if r.name],
            by_tool=(await self._tool_rows(since))[:_TOP],
            estimated_calls=await self._estimated_calls(since),
        )

    async def thread_usage(self, thread_id: str) -> ThreadUsage:
        query = """
            SELECT COUNT(*), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(cache_read_tokens), 0),
                   COALESCE(SUM(output_tokens), 0), (SELECT COUNT(*) FROM tool_calls WHERE thread_id = ?)
            FROM model_calls WHERE thread_id = ?
        """
        async with self._conn.execute(query, (thread_id, thread_id)) as cursor:
            row = await cursor.fetchone()
        return ThreadUsage(*row) if row else ThreadUsage()

    async def _token_rows(self, column: str, since: str) -> list[TokenRow]:
        """Rows per value of `column`, the most tokens first. Grouped by model too, since each has its price."""
        query = f"""
            SELECT {column}, model, COUNT(*), SUM(input_tokens), SUM(cache_read_tokens),
                   SUM(cache_write_tokens), SUM(output_tokens)
            FROM model_calls WHERE at >= ? GROUP BY {column}, model
        """
        async with self._conn.execute(query, (since,)) as cursor:
            rows = await cursor.fetchall()
        merged: dict[str, TokenRow] = {}
        for name, model, calls, tokens_in, read, write, tokens_out in rows:
            row = merged.setdefault(name or "", TokenRow(name or ""))
            row.calls += calls
            row.input_tokens += tokens_in
            row.cache_read_tokens += read
            row.cache_write_tokens += write
            row.output_tokens += tokens_out
            dollars = prices.cost(model, tokens_in, read, write, tokens_out)
            if dollars is not None:
                row.cost = (row.cost or 0.0) + dollars
        return sorted(merged.values(), key=lambda r: r.input_tokens + r.output_tokens, reverse=True)

    async def _tool_rows(self, since: str) -> list[TokenRow]:
        query = """
            SELECT p.name, COUNT(DISTINCT p.call_id), SUM(p.input_tokens), SUM(p.output_tokens)
            FROM token_parts p JOIN model_calls c ON c.id = p.call_id
            WHERE c.at >= ? AND p.kind = 'tool' GROUP BY p.name
            ORDER BY SUM(p.input_tokens) + SUM(p.output_tokens) DESC, p.name
        """
        async with self._conn.execute(query, (since,)) as cursor:
            rows = await cursor.fetchall()
        return [
            TokenRow(name, calls=calls, input_tokens=tokens_in, output_tokens=tokens_out)
            for name, calls, tokens_in, tokens_out in rows
        ]

    async def _estimated_calls(self, since: str) -> int:
        query = "SELECT COUNT(*) FROM model_calls WHERE at >= ? AND estimated = 1"
        async with self._conn.execute(query, (since,)) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

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
