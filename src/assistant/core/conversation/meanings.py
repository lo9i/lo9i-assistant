"""Conversations found by meaning, for routing from the inbox (dispatch.py): an older conversation a message
continues in other words than its tags' is still among those the model chooses from.

Each conversation's title, tags and first message are embedded with the local model (core/memory/e5.py) and
kept with the memories' vectors, as kind "conversation". A vector's key is the conversation's id with a
digest of that text, so a conversation retitled (core/conversation/titles.py) is embedded again and its old
vector dropped, as a deleted one's is. The daemon keeps them in step as conversations change, the way it
keeps the memories' (core/memory/indexer.py).
"""

import asyncio
import hashlib
import logging
from collections.abc import Sequence
from itertools import batched

from langgraph.store.base import BaseStore

from assistant.core import conversations
from assistant.core.bus import EventBus
from assistant.core.conversation.search import MessageIndex
from assistant.core.conversations import Conversation
from assistant.core.memory.embedder import Embedder, EmbeddingError
from assistant.core.memory.vectors import MemoryVectors
from assistant.core.waiting import first

logger = logging.getLogger(__name__)

KIND = "conversation"
# Texts embedded per model call.
_BATCH = 32
# How much of the first message goes in: enough to say what it was about.
_OPENING_CHARS = 500


class ConversationIndexer:
    name = "conversation index"

    def __init__(
        self, store: BaseStore, search: MessageIndex, vectors: MemoryVectors, embedder: Embedder, bus: EventBus
    ) -> None:
        self._store = store
        self._search = search
        self._vectors = vectors
        self._embedder = embedder
        self._bus = bus

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            # Taken before syncing, so a change made during the sync starts another one.
            after = self._bus.last_id
            await self._sync_logged()
            await first(stop.wait(), self._next_change(after))

    async def sync(self, user_id: str) -> int:
        """Embeds the conversations whose text changed and drops the vectors of those gone. Returns how many
        were embedded."""
        wanted = await self._texts(user_id)
        indexed = _models(await self._vectors.indexed(user_id))
        await self._vectors.remove(user_id, [(KIND, key) for key in indexed if key not in wanted])
        missing = [key for key in wanted if indexed.get(key) != self._embedder.model]
        for batch in batched(missing, _BATCH):
            vectors = await self._embedder.embed_passages([wanted[key] for key in batch])
            keyed = [((KIND, key), vector) for key, vector in zip(batch, vectors, strict=True)]
            await self._vectors.put(user_id, self._embedder.model, keyed)
        return len(missing)

    async def _texts(self, user_id: str) -> dict[str, str]:
        listed = [c for c in await conversations.recent(self._store, user_id) if not c.archived]
        openings = await self._search.first_user_messages(user_id, [c.thread_id for c in listed])
        texts = {c.thread_id: passage(c, openings.get(c.thread_id, "")) for c in listed}
        return {key_of(thread_id, text): text for thread_id, text in texts.items() if text}

    async def _sync_logged(self) -> None:
        """A failure (the model couldn't download) waits for the next change or restart."""
        try:
            embedded = sum([await self.sync(user_id) for user_id in await self._users()])
            if embedded:
                logger.info("Made %s conversations findable by meaning.", embedded)
        except Exception:
            logger.exception("Couldn't make conversations findable by meaning")

    async def _next_change(self, after: int) -> None:
        async for event in self._bus.subscribe(after):
            if event.kind == "conversations":
                return

    async def _users(self) -> set[str]:
        found = await self._store.alist_namespaces(prefix=("conversations",), max_depth=2)
        return {namespace[1] for namespace in found if len(namespace) == 2}


class SimilarConversations:
    def __init__(self, vectors: MemoryVectors, embedder: Embedder) -> None:
        self._vectors = vectors
        self._embedder = embedder

    async def nearest(self, user_id: str, text: str, among: Sequence[str], limit: int) -> list[str]:
        """The ids of the conversations among `among` closest in meaning to `text`, closest first. None until
        the index has some (the model is then loaded), and none when the model fails: routing goes on with
        the words and the most recent then."""
        if not among or not await self._vectors.any(user_id, KIND, self._embedder.model):
            return []
        try:
            vector = await self._embedder.embed_query(text)
        except EmbeddingError as e:
            logger.warning("Routing without meaning, the model failed: %s", e)
            return []
        ranked = await self._vectors.ranked(user_id, KIND, self._embedder.model, vector)
        allowed, closest = set(among), dict.fromkeys(thread_of(key) for key, _ in ranked)
        return [thread_id for thread_id in closest if thread_id in allowed][:limit]


def passage(conversation: Conversation, opening: str) -> str:
    """What a conversation is about: its title, its tags and how it began."""
    parts = [conversation.title, ", ".join(conversation.tags), " ".join(opening.split())[:_OPENING_CHARS]]
    return ". ".join(part for part in parts if part)


def key_of(thread_id: str, text: str) -> str:
    return f"{thread_id}#{hashlib.sha256(text.encode()).hexdigest()[:16]}"


def thread_of(key: str) -> str:
    return key.rsplit("#", 1)[0]


def _models(indexed: dict[tuple[str, str], str]) -> dict[str, str]:
    """The conversations' keys among the vectors, with the model that made each."""
    return {key: model for (kind, key), model in indexed.items() if kind == KIND}
