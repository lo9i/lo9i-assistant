"""SQLite storage: the LangGraph checkpointer (conversations) and store (long-term records).

Only the daemon opens the database, so a single file is enough. WAL mode lets the checkpointer
and the store each keep their own connection.
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite.aio import AsyncSqliteStore


@dataclass
class Storage:
    checkpointer: AsyncSqliteSaver
    store: AsyncSqliteStore


@asynccontextmanager
async def open_storage(path: str) -> AsyncIterator[Storage]:
    db = Path(path).expanduser()
    db.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncExitStack() as stack:
        checkpointer = AsyncSqliteSaver(await stack.enter_async_context(_connect(db)))
        store = AsyncSqliteStore(await stack.enter_async_context(_connect(db)))
        await checkpointer.setup()
        await store.setup()
        yield Storage(checkpointer=checkpointer, store=store)


@asynccontextmanager
async def _connect(db: Path) -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(db, isolation_level=None) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        yield conn
