"""SQLite storage: the LangGraph checkpointer (conversations) and store (long-term records).

Only the daemon opens the database, so a single file is enough. WAL mode lets the checkpointer,
the store, the usage log, the message search index and the memory vectors each keep their own connection.
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.base import Op, PutOp, Result
from langgraph.store.sqlite.aio import AsyncSqliteStore

from assistant.core.bus import EventBus
from assistant.core.conversation.search import MessageIndex
from assistant.core.memory.vectors import MemoryVectors
from assistant.core.usage.log import UsageLog

# Store namespaces, by their first part, and the event a change to them publishes.
_CHANGE_EVENTS = {
    "profile": "memory",
    "facts": "memory",
    "episodes": "memory",
    # Archived parts of conversations waiting for the memory writer (core/conversation/memory_writer.py).
    "memory_pending": "memory_pending",
    "integrations": "integrations",
    # Connected accounts (core/accounts.py) are integrations' settings too.
    "accounts": "integrations",
    "jobs": "jobs",
    "threads": "threads",
    "settings": "settings",
    "conversations": "conversations",
    # Each conversation's latest running summary (core/conversation/summaries.py), which routing embeds.
    "conversation_summaries": "conversation_summaries",
    # Job results and background work that ended (core/notifications.py).
    "notifications": "notifications",
    # Messages waiting to be sent in a conversation (core/conversation/queued.py), for the daemon to send.
    "queued_messages": "queued_messages",
    # Home's sections and their last results (core/home/).
    "home": "home",
    # The health checks' reports and the causes marked as known noise (core/doctor/).
    "doctor": "doctor",
    # Skills pinned to a conversation (core/conversation/pinned.py).
    "pinned_skills": "pinned_skills",
    # Conversations handed to a plugin's agent (core/conversation/handoffs.py).
    "handoffs": "handoffs",
    # Tasks whose end is still to be told (core/agent_tasks/reports.py), for the daemon to follow.
    "agent_task_reports": "agent_task_reports",
    "devices": "devices",
    "mcp_servers": "mcp",
    # Failures of MCP servers and skills (core/health.py), shown with them.
    "mcp_health": "mcp",
    "skill_health": "skills",
    # What the extras offer, kept between downloads (core/repositories/cache.py).
    "repository_listings": "plugins",
    # Removed plugins' kept keys (core/mcp/keys.py), which Settings lists.
    "plugin_keys": "plugins",
}


class NotifyingStore(AsyncSqliteStore):
    """The Store, publishing a bus event after every write, so clients learn about changes made
    in the background (archiving, scheduled jobs, pairing) without polling."""

    bus: EventBus

    @asynccontextmanager
    async def _cursor(self, *, transaction: bool = True) -> AsyncIterator[aiosqlite.Cursor]:
        """The library's, with two changes. Its transaction is a plain BEGIN that reads, then writes: in WAL
        mode, another connection committing in between fails the write at once with "database is locked",
        whatever the busy timeout. BEGIN IMMEDIATE takes the write lock first, waiting the busy timeout for it.
        And a batch that fails is rolled back instead of committed halfway."""
        if not self.is_setup:
            await self.setup()
        async with self.lock, self.conn.cursor() as cur:
            if not transaction:
                yield cur
                return
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield cur
            except BaseException:
                await self.conn.execute("ROLLBACK")
                raise
            await self.conn.execute("COMMIT")

    async def abatch(self, ops) -> list[Result]:
        ops = list(ops)
        results = await super().abatch(ops)
        for kind in sorted({k for op in ops if (k := _change_event(op))}):
            self.bus.publish(kind)
        return results


def _change_event(op: Op) -> str | None:
    if not isinstance(op, PutOp):
        return None
    return _CHANGE_EVENTS.get(op.namespace[0])


@dataclass
class Storage:
    checkpointer: AsyncSqliteSaver
    store: AsyncSqliteStore
    usage: UsageLog
    search: MessageIndex
    vectors: MemoryVectors


@asynccontextmanager
async def open_storage(path: str, bus: EventBus) -> AsyncIterator[Storage]:
    db = Path(path).expanduser()
    db.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncExitStack() as stack:
        checkpointer = AsyncSqliteSaver(await stack.enter_async_context(_connect(db)))
        store = NotifyingStore(await stack.enter_async_context(_connect(db)))
        store.bus = bus
        usage = UsageLog(await stack.enter_async_context(_connect(db)))
        search = MessageIndex(await stack.enter_async_context(_connect(db)))
        vectors = MemoryVectors(await stack.enter_async_context(_connect(db)))
        await checkpointer.setup()
        await store.setup()
        await usage.setup()
        await search.setup()
        await vectors.setup()
        yield Storage(checkpointer=checkpointer, store=store, usage=usage, search=search, vectors=vectors)


@asynccontextmanager
async def _connect(db: Path) -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(db, isolation_level=None) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        yield conn
