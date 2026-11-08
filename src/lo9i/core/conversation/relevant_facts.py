"""Saved facts that aren't basic come into a turn when the user's message is close to them in meaning: each user
message is embedded with the local model (core/memory/e5.py), whose vectors of the facts the memory index keeps
(core/memory/indexer.py), and the closest few above a similarity go in its turn header as a note. No model call.

A conversation keeps the facts it brought up: each comes once, and the system prompt of its later epochs lists them
(prompt.py), so one stays when the turn it came with is summarized away. The inbox keeps none: what it sends on
leaves its model calls (routed.py), so each message there gets its own, which go with it to where it's sent, and that
conversation keeps them."""

import logging
import re
from collections.abc import Collection, Sequence

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.store.base import BaseStore

from lo9i.core.attachments import Block
from lo9i.core.config import settings
from lo9i.core.conversation import prompts
from lo9i.core.conversation.turn_header import note_block
from lo9i.core.memory import facts
from lo9i.core.memory.embedder import EmbeddingError
from lo9i.core.memory.facts import Fact
from lo9i.core.memory.recall import MemoryRecall

logger = logging.getLogger(__name__)

_NOTE = prompts.load("relevant_facts_note")
_HEADING = _NOTE.splitlines()[0]
_LINE = re.compile(r"^- \[(\w+)\] ", re.MULTILINE)


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("relevant_facts", user_id)


async def kept(store: BaseStore, user_id: str, thread_id: str, messages: Sequence[BaseMessage] = ()) -> list[Fact]:
    """The facts the conversation brought up that still exist, in the order they came, but those the notes of
    `messages` (an epoch's) show."""
    shown = {i for m in messages if isinstance(m, HumanMessage) for i in ids_in(m.content)}
    return await facts.get(store, user_id, [i for i in await _kept_ids(store, user_id, thread_id) if i not in shown])


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """For a deleted conversation."""
    await store.adelete(_namespace(user_id), thread_id)


def ids_in(content: str | Sequence[Block | str]) -> list[str]:
    """The facts a message's notes brought (a message the inbox sent on carries its own)."""
    blocks = [] if isinstance(content, str) else content
    texts = [str(b.get("text", "")) for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
    return [fact_id for text in texts if _HEADING in text for fact_id in _LINE.findall(text)]


async def _kept_ids(store: BaseStore, user_id: str, thread_id: str) -> list[str]:
    item = await store.aget(_namespace(user_id), thread_id)
    return list(item.value.get("ids", [])) if item else []


class RelevantFacts:
    def __init__(self, store: BaseStore, recall: MemoryRecall) -> None:
        self._store = store
        self._recall = recall

    async def note(
        self, user_id: str, thread_id: str, text: str, keep: bool = True, carried: Collection[str] = ()
    ) -> list[Block]:
        """The turn header note with the facts close to `text` not shown yet, or nothing. `keep`: the conversation
        keeps them (not the inbox). `carried`: facts the message brought from the inbox, kept here too."""
        shown = {*carried, *(await _kept_ids(self._store, user_id, thread_id) if keep else [])}
        found = await self._close(user_id, text, shown)
        if keep and (found or carried):
            await self._keep(user_id, thread_id, [*carried, *(f.id for f in found)])
        return [note_block(_NOTE.format(facts=facts.render(found)))] if found else []

    async def _close(self, user_id: str, text: str, shown: set[str]) -> list[Fact]:
        """The facts neither the system prompt holds nor `shown` closest to `text`, closest first. A failing model only
        logs: the message goes on without them."""
        if not text.strip():
            return []
        try:
            scored = await self._recall.scored_facts(user_id, text)
        except EmbeddingError:
            logger.warning("Couldn't find the facts a message touches", exc_info=True)
            return []
        saved = await facts.load_all(self._store, user_id)
        in_prompt, _ = facts.in_prompt(saved, settings.memory_basic_facts_tokens)
        left_out = shown | {f.id for f in in_prompt}
        offered = {f.id: f for f in saved if f.id not in left_out}
        close = [offered[i] for i, score in scored if score >= settings.memory_relevant_similarity and i in offered]
        return close[: settings.memory_relevant_facts]

    async def _keep(self, user_id: str, thread_id: str, fact_ids: list[str]) -> None:
        ids = dict.fromkeys([*await _kept_ids(self._store, user_id, thread_id), *fact_ids])
        await self._store.aput(_namespace(user_id), thread_id, {"ids": list(ids)})
