"""Postgres connection pool, LangGraph checkpointer (conversations) and store (long-term records)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


@dataclass
class Storage:
    pool: AsyncConnectionPool
    checkpointer: AsyncPostgresSaver
    store: AsyncPostgresStore


@asynccontextmanager
async def open_storage(database_url: str) -> AsyncIterator[Storage]:
    async with AsyncConnectionPool(
        database_url,
        open=False,
        max_size=20,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    ) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        store = AsyncPostgresStore(pool)
        await checkpointer.setup()
        await store.setup()
        yield Storage(pool=pool, checkpointer=checkpointer, store=store)
