"""Digests archived parts of conversations (pending.py) into memory: an episode, profile updates
and facts (digest.py). Off the reply's path, so a new epoch waits only for its summary.

The daemon runs it as a supervised task: it writes at start, which catches parts the daemon stopped
before digesting, and again after every new part. One part at a time, so two digests never save
over each other's profile. A part that fails stays, and is tried again at the next change or start.
Stopping cuts a digest short, so a model call that never answers can't hold the daemon's restart:
the part stays and is written at the next start.
"""

import asyncio
import logging
from collections.abc import Callable, Sequence
from typing import Protocol

from langchain_core.messages import BaseMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from assistant.core.bus import EventBus
from assistant.core.config import settings
from assistant.core.conversation import pending
from assistant.core.conversation.digest import Digester, DigestInput, MemoryDigest
from assistant.core.conversation.display import shown
from assistant.core.conversation.pending import PendingPart
from assistant.core.conversation.transcript import render
from assistant.core.memory import episodes, facts, profile
from assistant.core.memory.embedder import EmbeddingError
from assistant.core.memory.facts import Fact
from assistant.core.waiting import first

logger = logging.getLogger(__name__)

# Saved facts closest to each of the user's messages, given to the digest besides the most recent ones.
_RELATED_PER_MESSAGE = 3
# The user's messages they're looked up for: the latest of the part.
_MESSAGES_LOOKED_UP = 20


class RelatedFacts(Protocol):
    async def facts_near(self, user_id: str, texts: Sequence[str], limit_each: int) -> list[Fact]: ...


class MemoryWriter:
    name = "memory writer"

    def __init__(
        self,
        store: BaseStore,
        checkpointer: BaseCheckpointSaver,
        bus: EventBus,
        digester: Callable[[], Digester],
        related: RelatedFacts,
    ) -> None:
        """`digester` gives the current one: it changes with the model. `related` finds saved facts by meaning."""
        self._store = store
        self._checkpointer = checkpointer
        self._bus = bus
        self._digester = digester
        self._related = related

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            # Taken before writing, so a part added during the write starts another one.
            after = self._bus.last_id
            await first(stop.wait(), self.write_all())
            await first(stop.wait(), self._next_part(after))

    async def write_all(self) -> None:
        for user_id in await pending.users(self._store):
            for part in await pending.load_all(self._store, user_id):
                await self._write_logged(user_id, part)

    async def _write_logged(self, user_id: str, part: PendingPart) -> None:
        try:
            await self._write(user_id, part)
        except Exception:
            logger.exception("Couldn't save memory from conversation %s", part.thread_id)

    async def _write(self, user_id: str, part: PendingPart) -> None:
        """A part whose conversation was deleted has no messages left, and nothing to learn."""
        messages = (await self._messages(part.thread_id))[part.start : part.end]
        if messages:
            digest = await self._digester()(await self._input(user_id, part, messages))
            await self._save(user_id, part, digest)
        await pending.remove(self._store, user_id, part)

    async def _messages(self, thread_id: str) -> list[BaseMessage]:
        saved = await self._checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
        return saved.checkpoint["channel_values"].get("messages", []) if saved else []

    async def _input(self, user_id: str, part: PendingPart, messages: Sequence[BaseMessage]) -> DigestInput:
        return DigestInput(
            previous_summary=part.previous_summary,
            profile=await profile.load(self._store, user_id),
            facts=await self._facts(user_id, messages),
            transcript=render(messages),
        )

    async def _facts(self, user_id: str, messages: Sequence[BaseMessage]) -> list[Fact]:
        """The most recent facts, and older ones close to what the user said, so the digest neither saves
        again what's known nor misses a saved fact the part shows is outdated."""
        recent = await facts.load(self._store, user_id, settings.memory_max_facts)
        known = {f.id for f in recent}
        return [*recent, *(f for f in await self._near(user_id, messages) if f.id not in known)]

    async def _near(self, user_id: str, messages: Sequence[BaseMessage]) -> list[Fact]:
        """Without the embedding model (still downloading, or failing), the digest gets the recent facts only."""
        said = [m.text for m in shown(messages) if m.role == "user" and m.text.strip()][-_MESSAGES_LOOKED_UP:]
        try:
            return await self._related.facts_near(user_id, said, _RELATED_PER_MESSAGE)
        except EmbeddingError:
            logger.warning("Couldn't look up saved facts related to conversation; digesting with recent ones only.")
            return []

    async def _save(self, user_id: str, part: PendingPart, digest: MemoryDigest) -> None:
        await profile.save(self._store, user_id, digest.profile)
        for text in digest.new_facts:
            await facts.add(self._store, user_id, text)
        for fact_id in digest.outdated_fact_ids:
            await facts.remove(self._store, user_id, fact_id)
        await episodes.save(
            self._store, user_id, episodes.Episode(part.started_at, part.ended_at, digest.episode_summary)
        )

    async def _next_part(self, after: int) -> None:
        async for event in self._bus.subscribe(after):
            if event.kind == "memory_pending":
                return
