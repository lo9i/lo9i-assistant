"""Finds saved facts and episodes by meaning, for search_memory and the memory digest."""

from collections.abc import Sequence
from dataclasses import dataclass

from langgraph.store.base import BaseStore

from lo9i.core.memory import episodes, facts
from lo9i.core.memory.embedder import Embedder
from lo9i.core.memory.episodes import Episode
from lo9i.core.memory.facts import Fact
from lo9i.core.memory.vectors import MemoryVectors


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

    async def facts_near(self, user_id: str, texts: Sequence[str], limit_each: int) -> list[Fact]:
        """The saved facts closest to each text, once each, in the texts' order. Raises EmbeddingError."""
        found: dict[str, None] = {}
        for text in texts:
            vector = await self._embedder.embed_query(text)
            found.update(dict.fromkeys(await self._nearest(user_id, "fact", vector, limit_each)))
        return await facts.get(self._store, user_id, list(found))

    async def scored(self, user_id: str, text: str, kinds: Sequence[str]) -> dict[str, list[tuple[str, float]]]:
        """Each kind's indexed memories ("fact", "episode") with how close they are to `text` (the cosine similarity),
        closest first; `text` is embedded once, and not at all before any of them is indexed, so the model isn't
        loaded for nothing. Raises EmbeddingError."""
        model = self._embedder.model
        indexed = [kind for kind in kinds if await self._vectors.any(user_id, kind, model)]
        if not indexed:
            return {kind: [] for kind in kinds}
        vector = await self._embedder.embed_query(text)
        ranked = {kind: await self._vectors.ranked(user_id, kind, model, vector) for kind in indexed}
        return {kind: ranked.get(kind, []) for kind in kinds}

    async def _nearest(self, user_id: str, kind: str, vector: list[float], limit: int) -> list[str]:
        return await self._vectors.nearest(user_id, kind, self._embedder.model, vector, limit)
