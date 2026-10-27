"""Full-text search over what the user and the assistant wrote in every conversation (SQLite FTS5).

The checkpoints keep messages as serialized state, which SQLite can't search, so each finished run
adds its new messages here as plain text: the user's words without turn headers, and the
assistant's replies. Tool calls and their outputs are left out. Each conversation records how many
of its messages are indexed, so a run that wasn't indexed is caught up by the next one.
"""

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass

import aiosqlite
from langchain_core.messages import BaseMessage, HumanMessage

from assistant.core.conversation.display import shown
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
CREATE TABLE IF NOT EXISTS message_search_progress (
    thread_id TEXT PRIMARY KEY,
    indexed_upto INTEGER NOT NULL
);
"""

# Words around each match shown in a result.
_SNIPPET_WORDS = 32
# What's indexed of a message as shown: not tool calls, nor a quick exchange carried from the inbox, which
# the inbox's own messages already are.
_SAID = {"user", "assistant", "thinking", "brief"}


@dataclass(frozen=True)
class Found:
    thread_id: str
    role: str  # user | assistant
    # Local time of the turn ("2026-09-30 14:05"), from its turn header; empty when it had none.
    at: str
    snippet: str


@dataclass(frozen=True)
class _Row:
    role: str
    at: str
    text: str


class MessageIndex:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn
        # Runs in different conversations index at the same time, on this one connection; each
        # transaction holds it, so none begins inside another.
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        await self._conn.executescript(_SCHEMA)

    async def add(self, user_id: str, thread_id: str, messages: Sequence[BaseMessage]) -> int:
        """Indexes the messages not indexed yet; `messages` is the conversation's whole history.
        Returns how many were added."""
        async with self._lock:
            rows = _rows(messages, await self._indexed_upto(thread_id))
            await self._conn.execute("BEGIN")
            try:
                await self._write(user_id, thread_id, rows, len(messages))
            except BaseException:
                await self._conn.execute("ROLLBACK")
                raise
            await self._conn.execute("COMMIT")
        return len(rows)

    async def _write(self, user_id: str, thread_id: str, rows: list[_Row], upto: int) -> None:
        await self._conn.executemany(
            "INSERT INTO message_search (text, user_id, thread_id, role, at) VALUES (?, ?, ?, ?, ?)",
            [(r.text, user_id, thread_id, r.role, r.at) for r in rows],
        )
        await self._conn.execute(
            "INSERT INTO message_search_progress (thread_id, indexed_upto) VALUES (?, ?) "
            "ON CONFLICT (thread_id) DO UPDATE SET indexed_upto = excluded.indexed_upto",
            (thread_id, upto),
        )

    async def search(self, user_id: str, query: str, limit: int) -> list[Found]:
        """The best matches first. Any of the query's words matches; messages with more of them,
        and rarer ones, rank higher."""
        match = _match(query)
        if not match:
            return []
        sql = (
            f"SELECT thread_id, role, at, snippet(message_search, 0, '', '', '…', {_SNIPPET_WORDS}) "
            "FROM message_search WHERE message_search MATCH ? AND user_id = ? ORDER BY rank LIMIT ?"
        )
        async with self._conn.execute(sql, (match, user_id, limit)) as cursor:
            return [Found(*row) for row in await cursor.fetchall()]

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
            await self._conn.execute("DELETE FROM message_search_progress WHERE thread_id = ?", (thread_id,))

    async def _indexed_upto(self, thread_id: str) -> int:
        sql = "SELECT indexed_upto FROM message_search_progress WHERE thread_id = ?"
        async with self._conn.execute(sql, (thread_id,)) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0


def _rows(messages: Sequence[BaseMessage], start: int) -> list[_Row]:
    """Rows for the messages from `start` on. A reply takes the time of the user message before it,
    which may come before `start` (a run resumed after an approval)."""
    rows: list[_Row] = []
    at = ""
    for position, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            at = sent_at(message) or at
        if position >= start:
            rows += [_Row(m.role, at, m.text) for m in shown([message]) if m.role in _SAID and m.text]
    return rows


def _match(query: str) -> str:
    """Each word quoted, so punctuation and FTS5 keywords (AND, NEAR) in the query are plain words."""
    return " OR ".join(f'"{word}"' for word in re.findall(r"\w+", query))
