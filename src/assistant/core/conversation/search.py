"""Full-text search over every conversation (SQLite FTS5): what the user and the assistant wrote, and what
tools answered.

The checkpoints keep messages as serialized state, which SQLite can't search, so each finished run
adds its new messages here as plain text: the user's words without turn headers, and the
assistant's replies. Tool outputs go in a table of their own (the assistant's, a subagent's and a
handed-off agent's), so they never crowd out what was said, nor make a conversation match the search box
for words only a page it read had. Each conversation records how many of its messages are indexed in
each, so a run that wasn't indexed is caught up by the next one, and conversations indexed before tool
outputs were are caught up at start.
"""

import asyncio
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import aiosqlite
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from assistant.core import subagent_steps
from assistant.core.conversation.display import agent_tool_calls, shown
from assistant.core.conversation.turn_header import sent_at

# unicode61 with diacritics removed, so "camion" finds "camión".
_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS message_search USING fts5(
    text,
    user_id UNINDEXED,
    thread_id UNINDEXED,
    role UNINDEXED,
    at UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE VIRTUAL TABLE IF NOT EXISTS tool_output_search USING fts5(
    text,
    user_id UNINDEXED,
    thread_id UNINDEXED,
    tool UNINDEXED,
    at UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS message_search_progress (
    thread_id TEXT PRIMARY KEY,
    indexed_upto INTEGER NOT NULL,
    tools_indexed_upto INTEGER NOT NULL DEFAULT 0
);
"""
_TOOLS_PROGRESS = "tools_indexed_upto"

# Words around each match shown in a result.
_SNIPPET_WORDS = 32
# What's indexed of a message as shown: not tool calls, nor a quick exchange carried from the inbox, which
# the inbox's own messages already are.
_SAID = {"user", "assistant", "thinking", "brief"}
# The most of one tool output indexed: a page or a log past this is rarely searched for its end, and the index
# would grow by every page read.
_MAX_TOOL_OUTPUT = 20_000
# Tools whose outputs copy what's kept elsewhere: the search's own results, a skill's instructions, a list of
# tools.
_COPIES = {"search_memory", "use_skill", "list_skills", "load_tools"}


@dataclass(frozen=True)
class Found:
    thread_id: str
    # user | assistant, or for a tool output the tool's name.
    role: str
    # Local time of the turn ("2026-09-30 14:05"), from its turn header; empty when it had none.
    at: str
    snippet: str


@dataclass(frozen=True)
class _Row:
    # user | assistant, or the tool's name.
    role: str
    at: str
    text: str


@dataclass(frozen=True)
class _Progress:
    said: int
    tools: int


class MessageIndex:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn
        # Runs in different conversations index at the same time, on this one connection; each
        # transaction holds it, so none begins inside another.
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        await self._conn.executescript(_SCHEMA)
        await self._add_tools_progress()

    async def _add_tools_progress(self) -> None:
        """To a progress table from before tool outputs were indexed: 0 for each conversation, so the catch-up at
        start indexes their tool outputs."""
        async with self._conn.execute("PRAGMA table_info(message_search_progress)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        if _TOOLS_PROGRESS not in columns:
            await self._conn.execute(
                f"ALTER TABLE message_search_progress ADD COLUMN {_TOOLS_PROGRESS} INTEGER NOT NULL DEFAULT 0"
            )

    async def add(self, user_id: str, thread_id: str, messages: Sequence[BaseMessage]) -> int:
        """Indexes the messages and tool outputs not indexed yet; `messages` is the conversation's whole
        history. Returns how many were added."""
        async with self._lock:
            progress = await self._indexed_upto(thread_id)
            said, outputs = _rows(messages, progress.said, _said), _rows(messages, progress.tools, _outputs)
            await self._conn.execute("BEGIN")
            try:
                await self._write(user_id, thread_id, said, outputs, len(messages))
            except BaseException:
                await self._conn.execute("ROLLBACK")
                raise
            await self._conn.execute("COMMIT")
        return len(said) + len(outputs)

    async def _write(self, user_id: str, thread_id: str, said: list[_Row], outputs: list[_Row], upto: int) -> None:
        await self._conn.executemany(
            "INSERT INTO message_search (text, user_id, thread_id, role, at) VALUES (?, ?, ?, ?, ?)",
            [(r.text, user_id, thread_id, r.role, r.at) for r in said],
        )
        await self._conn.executemany(
            "INSERT INTO tool_output_search (text, user_id, thread_id, tool, at) VALUES (?, ?, ?, ?, ?)",
            [(r.text, user_id, thread_id, r.role, r.at) for r in outputs],
        )
        await self._conn.execute(
            f"INSERT INTO message_search_progress (thread_id, indexed_upto, {_TOOLS_PROGRESS}) VALUES (?, ?, ?) "
            f"ON CONFLICT (thread_id) DO UPDATE SET indexed_upto = excluded.indexed_upto, "
            f"{_TOOLS_PROGRESS} = excluded.{_TOOLS_PROGRESS}",
            (thread_id, upto, upto),
        )

    async def search(self, user_id: str, query: str, limit: int) -> list[Found]:
        """What the user and the assistant wrote, the best matches first. Any of the query's words matches;
        messages with more of them, and rarer ones, rank higher."""
        return await self._search("message_search", "role", user_id, query, limit)

    async def search_tool_outputs(self, user_id: str, query: str, limit: int) -> list[Found]:
        """What tools answered, ranked as `search` ranks messages; each found with its tool's name as its role."""
        return await self._search("tool_output_search", "tool", user_id, query, limit)

    async def _search(self, table: str, role: str, user_id: str, query: str, limit: int) -> list[Found]:
        match = _match(query)
        if not match:
            return []
        sql = (
            f"SELECT thread_id, {role}, at, snippet({table}, 0, '', '', '…', {_SNIPPET_WORDS}) "
            f"FROM {table} WHERE {table} MATCH ? AND user_id = ? ORDER BY rank LIMIT ?"
        )
        async with self._conn.execute(sql, (match, user_id, limit)) as cursor:
            return [Found(*row) for row in await cursor.fetchall()]

    async def threads_with(self, user_id: str, text: str) -> list[str]:
        """The conversations with a message holding every word of `text`, each as the start of a word, so a
        search box finds them as it's typed ("hack" finds "Hacker News")."""
        match = _match_all_prefixes(text)
        if not match:
            return []
        sql = "SELECT DISTINCT thread_id FROM message_search WHERE message_search MATCH ? AND user_id = ?"
        async with self._conn.execute(sql, (match, user_id)) as cursor:
            return [thread_id for (thread_id,) in await cursor.fetchall()]

    async def first_user_messages(self, user_id: str, thread_ids: Sequence[str]) -> dict[str, str]:
        """Each conversation's first user message, as indexed; one not indexed yet is left out."""
        if not thread_ids:
            return {}
        marks = ", ".join("?" for _ in thread_ids)
        sql = (
            "SELECT thread_id, text FROM message_search WHERE rowid IN (SELECT min(rowid) FROM message_search "
            f"WHERE user_id = ? AND role = 'user' AND thread_id IN ({marks}) GROUP BY thread_id)"
        )
        async with self._conn.execute(sql, (user_id, *thread_ids)) as cursor:
            return {thread_id: text for thread_id, text in await cursor.fetchall()}

    async def remove(self, thread_id: str) -> None:
        async with self._lock:
            await self._conn.execute("DELETE FROM message_search WHERE thread_id = ?", (thread_id,))
            await self._conn.execute("DELETE FROM tool_output_search WHERE thread_id = ?", (thread_id,))
            await self._conn.execute("DELETE FROM message_search_progress WHERE thread_id = ?", (thread_id,))

    async def _indexed_upto(self, thread_id: str) -> _Progress:
        sql = f"SELECT indexed_upto, {_TOOLS_PROGRESS} FROM message_search_progress WHERE thread_id = ?"
        async with self._conn.execute(sql, (thread_id,)) as cursor:
            row = await cursor.fetchone()
        return _Progress(int(row[0]), int(row[1])) if row else _Progress(0, 0)


def _rows(
    messages: Sequence[BaseMessage], start: int, texts: Callable[[BaseMessage], list[tuple[str, str]]]
) -> list[_Row]:
    """Rows for the messages from `start` on, from each one's (role, text) pairs. A reply takes the time of the
    user message before it, which may come before `start` (a run resumed after an approval)."""
    rows: list[_Row] = []
    at = ""
    for position, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            at = sent_at(message) or at
        if position >= start:
            rows += [_Row(role, at, text) for role, text in texts(message) if text.strip()]
    return rows


def _said(message: BaseMessage) -> list[tuple[str, str]]:
    return [(m.role, m.text) for m in shown([message]) if m.role in _SAID]


def _outputs(message: BaseMessage) -> list[tuple[str, str]]:
    """Each tool's name and output: a tool's result with the steps a subagent or a task took for it, and a
    handed-off agent's calls in its reply with their own subagents' steps."""
    if isinstance(message, ToolMessage):
        steps = [(s.name, s.output) for s in subagent_steps.of(message)]
        found = [(message.name or "tool", message.text), *steps]
    elif isinstance(message, AIMessage):
        calls = agent_tool_calls(message)
        found = [(c.text, c.output) for c in calls] + [(s.name, s.output) for c in calls for s in c.steps]
    else:
        found = []
    return [(name, output[:_MAX_TOOL_OUTPUT]) for name, output in found if name not in _COPIES]


def _match(query: str) -> str:
    """Each word quoted, so punctuation and FTS5 keywords (AND, NEAR) in the query are plain words."""
    return " OR ".join(f'"{word}"' for word in re.findall(r"\w+", query))


def _match_all_prefixes(text: str) -> str:
    """Every word as a quoted prefix, which FTS5 joins with AND."""
    return " ".join(f'"{word}"*' for word in re.findall(r"\w+", text))
