"""The Store's batches read, then write, while other connections write to the same file: a batch takes the write
lock before it reads, so a write committed in between can't fail it, and a batch that fails writes nothing."""

import asyncio

import aiosqlite
import pytest
from langgraph.store.base import PutOp

from assistant.core.bus import EventBus
from assistant.core.storage import open_storage

# Long enough for a write on another connection that isn't held back to commit.
_COMMITS_WITHIN = 0.5


async def _write_elsewhere(path: str) -> None:
    async with aiosqlite.connect(path, isolation_level=None) as conn:
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("INSERT INTO store (prefix, key, value) VALUES ('elsewhere', 'k', '{}')")


async def test_a_write_committed_between_a_batchs_read_and_its_write_doesnt_fail_it(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    path = str(tmp_path / "lo9i.db")
    async with open_storage(path, EventBus()) as storage:
        store = storage.store
        read = type(store)._batch_get_ops
        elsewhere: list[asyncio.Task] = []

        async def _read_then_someone_writes(self, *args):
            await read(self, *args)
            elsewhere.append(asyncio.create_task(_write_elsewhere(path)))
            await asyncio.wait(elsewhere, timeout=_COMMITS_WITHIN)

        monkeypatch.setattr(type(store), "_batch_get_ops", _read_then_someone_writes)
        await asyncio.gather(store.aget(("profile", "u"), "profile"), store.aput(("profile", "u"), "profile", {"a": 1}))
        await asyncio.gather(*elsewhere)
        monkeypatch.undo()
        saved = await store.aget(("profile", "u"), "profile")
        assert saved is not None and saved.value == {"a": 1}


async def test_a_batch_that_fails_after_writing_keeps_nothing_of_it(tmp_path, monkeypatch: pytest.MonkeyPatch):
    async with open_storage(str(tmp_path / "lo9i.db"), EventBus()) as storage:
        store = storage.store
        write = type(store)._batch_put_ops

        async def _fails_after_writing(self, *args):
            await write(self, *args)
            raise RuntimeError("broke halfway")

        monkeypatch.setattr(type(store), "_batch_put_ops", _fails_after_writing)
        with pytest.raises(RuntimeError):
            await store.abatch([PutOp(("notes", "u"), "n", {"text": "half"})])
        monkeypatch.undo()
        assert await store.aget(("notes", "u"), "n") is None
