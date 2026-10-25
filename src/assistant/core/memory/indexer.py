"""Keeps the memory vectors (vectors.py) in step with the facts and episodes in the Store.

The daemon runs it as a supervised task: it syncs at start, which also catches up on memories
saved before search existed, and again after every memory change the bus reports. A sync embeds
what has no vector yet (or one from another model) and drops vectors of deleted memories, so a
failed sync is simply repeated by the next one.
"""

import asyncio
import logging
from itertools import batched

from langgraph.store.base import BaseStore

from assistant.core.bus import EventBus
from assistant.core.memory import episodes, facts
from assistant.core.memory.embedder import Embedder
from assistant.core.memory.vectors import MemoryKey, MemoryVectors
from assistant.core.waiting import first

logger = logging.getLogger(__name__)

# Texts embedded per model call.
_BATCH = 32
# The vectors this indexer keeps; others in the table (conversations, core/conversation/meanings.py) aren't its own.
_KINDS = ("fact", "episode")


class MemoryIndexer:
    name = "memory index"

    def __init__(self, store: BaseStore, vectors: MemoryVectors, embedder: Embedder, bus: EventBus) -> None:
        self._store = store
        self._vectors = vectors
        self._embedder = embedder
        self._bus = bus

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            # Taken before syncing, so a change made during the sync starts another one.
            after = self._bus.last_id
            await self._sync_logged()
            await first(stop.wait(), self._next_change(after))

    async def sync_all(self) -> int:
        """Syncs every user with memories. Returns how many memories were embedded."""
        return sum([await self.sync(user_id) for user_id in await self._users()])

    async def sync(self, user_id: str) -> int:
        wanted = await self._memories(user_id)
        indexed = {key: model for key, model in (await self._vectors.indexed(user_id)).items() if key[0] in _KINDS}
        await self._vectors.remove(user_id, [key for key in indexed if key not in wanted])
        missing = [key for key in wanted if indexed.get(key) != self._embedder.model]
        for batch in batched(missing, _BATCH):
            vectors = await self._embedder.embed_passages([wanted[key] for key in batch])
            await self._vectors.put(user_id, self._embedder.model, zip(batch, vectors, strict=True))
        return len(missing)

    async def _sync_logged(self) -> None:
        """A failure (the model couldn't download) waits for the next change or restart."""
        try:
            if embedded := await self.sync_all():
                logger.info("Made %s memories searchable.", embedded)
        except Exception:
            logger.exception("Couldn't make memories searchable")

    async def _next_change(self, after: int) -> None:
        async for event in self._bus.subscribe(after):
            if event.kind == "memory":
                return

    async def _memories(self, user_id: str) -> dict[MemoryKey, str]:
        saved = {("fact", f.id): f.text for f in await facts.load_all(self._store, user_id)}
        return saved | {("episode", e.id): e.summary for e in await episodes.load_all(self._store, user_id)}

    async def _users(self) -> set[str]:
        found = [await self._store.alist_namespaces(prefix=(kind,), max_depth=2) for kind in ("facts", "episodes")]
        return {namespace[1] for listed in found for namespace in listed if len(namespace) == 2}
