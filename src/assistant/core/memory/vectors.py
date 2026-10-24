"""The vectors of saved facts and episodes, and of conversations (core/conversation/meanings.py), in their own
SQLite table.

Kept apart from the Store, so saving a memory never waits on (or fails with) the embedding model:
the indexer (indexer.py) embeds what's new in the background.
"""

from collections.abc import Iterable

import aiosqlite
import numpy as np

# A memory by its kind ("fact", "episode", or "conversation") and its key.
MemoryKey = tuple[str, str]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_vectors (
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding BLOB NOT NULL,
    PRIMARY KEY (user_id, kind, key)
);
"""


class MemoryVectors:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def setup(self) -> None:
        await self._conn.executescript(_SCHEMA)

    async def indexed(self, user_id: str) -> dict[MemoryKey, str]:
        """Every memory with a vector, and the model that made it."""
        sql = "SELECT kind, key, model FROM memory_vectors WHERE user_id = ?"
        async with self._conn.execute(sql, (user_id,)) as cursor:
            return {(kind, key): model for kind, key, model in await cursor.fetchall()}

    async def put(self, user_id: str, model: str, vectors: Iterable[tuple[MemoryKey, list[float]]]) -> None:
        await self._conn.executemany(
            "INSERT OR REPLACE INTO memory_vectors (user_id, kind, key, model, embedding) VALUES (?, ?, ?, ?, ?)",
            [(user_id, kind, key, model, _blob(v)) for (kind, key), v in vectors],
        )

    async def remove(self, user_id: str, keys: Iterable[MemoryKey]) -> None:
        await self._conn.executemany(
            "DELETE FROM memory_vectors WHERE user_id = ? AND kind = ? AND key = ?",
            [(user_id, kind, key) for kind, key in keys],
        )

    async def nearest(self, user_id: str, kind: str, model: str, vector: list[float], limit: int) -> list[str]:
        """Keys of the memories of `kind` closest in meaning to `vector`, closest first."""
        return [key for key, _ in await self.ranked(user_id, kind, model, vector)][:limit]

    async def ranked(self, user_id: str, kind: str, model: str, vector: list[float]) -> list[tuple[str, float]]:
        """Every key of `kind` with how close it is to `vector` (the cosine similarity), closest first.

        Compared in numpy rather than with a SQLite vector extension: Python builds often can't load
        extensions, and a few thousand vectors take about a millisecond."""
        sql = "SELECT key, embedding FROM memory_vectors WHERE user_id = ? AND kind = ? AND model = ?"
        async with self._conn.execute(sql, (user_id, kind, model)) as cursor:
            rows = list(await cursor.fetchall())
        if not rows:
            return []
        # The vectors are normalized, so the dot product is the cosine similarity.
        scores = np.stack([np.frombuffer(blob, dtype=np.float32) for _, blob in rows]) @ np.asarray(
            vector, dtype=np.float32
        )
        return [(rows[i][0], float(scores[i])) for i in np.argsort(-scores)]

    async def any(self, user_id: str, kind: str, model: str) -> bool:
        """Whether any vector of `kind` was made by `model`."""
        sql = "SELECT 1 FROM memory_vectors WHERE user_id = ? AND kind = ? AND model = ? LIMIT 1"
        async with self._conn.execute(sql, (user_id, kind, model)) as cursor:
            return await cursor.fetchone() is not None


def _blob(vector: list[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()
