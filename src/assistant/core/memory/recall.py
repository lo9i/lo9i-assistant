"""Finds saved facts and episodes by meaning, for search_memory."""

from dataclasses import dataclass

from langgraph.store.base import BaseStore

from assistant.core.memory import episodes, facts
from assistant.core.memory.embedder import Embedder
from assistant.core.memory.episodes import Episode
from assistant.core.memory.facts import Fact
from assistant.core.memory.vectors import MemoryVectors


@dataclass(frozen=True)
class Recalled:
    facts: list[Fact]
    episodes: list[Episode]


class MemoryRecall:
    def __init__(self, store: BaseStore, vectors: MemoryVectors, embedder: Embedder) -> None:
        self._store = store
        self._vectors = vectors
        self._embedder = embedder

    async def search(self, user_id: str, query: str, limit_facts: int, limit_episodes: int) -> Recalled:
        """The closest first. Raises EmbeddingError when the query can't be embedded. A memory
        deleted since the last index sync is left out."""
        vector = await self._embedder.embed_query(query)
        fact_ids = await self._nearest(user_id, "fact", vector, limit_facts)
        episode_ids = await self._nearest(user_id, "episode", vector, limit_episodes)
        return Recalled(
            facts=await facts.get(self._store, user_id, fact_ids),
            episodes=await episodes.get(self._store, user_id, episode_ids),
        )

    async def _nearest(self, user_id: str, kind: str, vector: list[float], limit: int) -> list[str]:
        return await self._vectors.nearest(user_id, kind, self._embedder.model, vector, limit)
