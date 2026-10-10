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
}


class NotifyingStore(AsyncSqliteStore):
    """The Store, publishing a bus event after every write, so clients learn about changes made
    in the background (archiving, scheduled jobs, pairing) without polling."""

    bus: EventBus

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
