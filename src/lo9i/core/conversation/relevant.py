"""Memories that come into a turn when the user's message is close to them in meaning: saved facts that aren't basic
(core/memory/facts.py) and summaries of past conversations. Each user message is embedded with the local model
(core/memory/e5.py), whose vectors of the memories the memory index keeps (core/memory/indexer.py), and the closest few
of each kind above its similarity go in its turn header as a note. No model call.

A conversation keeps what it brought up: each comes once, and the system prompt of its later epochs lists them
(prompt.py), so one stays when the turn it came with is summarized away. The inbox keeps none: what it sends on
leaves its model calls (routed.py), so each message there gets its own, which go with it to where it's sent, and that
conversation keeps them."""

import logging
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.store.base import BaseStore

from lo9i.core.attachments import Block
from lo9i.core.config import settings
from lo9i.core.conversation import prompts
from lo9i.core.conversation.turn_header import note_block
from lo9i.core.memory import episodes, facts
from lo9i.core.memory.embedder import EmbeddingError
from lo9i.core.memory.episodes import Episode
from lo9i.core.memory.facts import Fact
from lo9i.core.memory.recall import MemoryRecall

logger = logging.getLogger(__name__)

# The memory index's kinds of vectors.
Kind = Literal["fact", "episode"]
_KINDS: tuple[Kind, ...] = ("fact", "episode")


@dataclass(frozen=True)
class Brought:
    """What a conversation brought up, in the order it came."""

    facts: list[Fact] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)


@dataclass(frozen=True)
class _Rule:
    note: str
    most: Callable[[], int]
    similarity: Callable[[], float]
    # How far above the median of every memory of the kind a score has to be; 0 for none.
    margin: Callable[[], float]

    @property
    def heading(self) -> str:
        return self.note.splitlines()[0]


_RULES: dict[Kind, _Rule] = {
    "fact": _Rule(
        prompts.load("relevant_facts_note"),
        lambda: settings.memory_relevant_facts,
        lambda: settings.memory_relevant_similarity,
        lambda: 0.0,
    ),
    "episode": _Rule(
        prompts.load("relevant_conversations_note"),
        lambda: settings.memory_relevant_conversations,
        lambda: settings.memory_relevant_conversations_similarity,
        lambda: settings.memory_relevant_conversations_margin,
    ),
}


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("relevant_memories", user_id)


async def kept(store: BaseStore, user_id: str, thread_id: str, messages: Sequence[BaseMessage] = ()) -> Brought:
    """What the conversation brought up that still exists, but what the notes of `messages` (an epoch's) show."""
    record = await _record(store, user_id, thread_id)
    notes = [_text(m.content) for m in messages if isinstance(m, HumanMessage)]
    found = await facts.get(store, user_id, record["fact"])
    summaries = await episodes.get(store, user_id, record["episode"])
    return Brought(
        facts=[f for f in found if not _shown("fact", facts.line(f), notes)],
        episodes=[e for e in summaries if not _shown("episode", episodes.line(e), notes)],
    )


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """For a deleted conversation."""
    await store.adelete(_namespace(user_id), thread_id)


class RelevantMemories:
    def __init__(self, store: BaseStore, recall: MemoryRecall) -> None:
        self._store = store
        self._recall = recall

    async def notes(
        self, user_id: str, thread_id: str, text: str, keep: bool = True, carried: Sequence[Block | str] = ()
    ) -> list[Block]:
        """The turn header's notes with the memories close to `text` not shown yet, or nothing. `keep`: the
        conversation keeps them (not the inbox). `carried`: the content of a message the inbox sent on, whose notes
        brought their own, which aren't shown again and are kept here too."""
        offered = await self._offered(user_id)
        record = await _record(self._store, user_id, thread_id) if keep else _none()
        brought: dict[Kind, list[str]] = {kind: _carried(kind, offered[kind], [_text(carried)]) for kind in _KINDS}
        shown: dict[Kind, set[str]] = {kind: {*record[kind], *brought[kind]} for kind in _KINDS}
        found = await self._close(user_id, text, offered, shown)
        if keep and (any(found.values()) or any(brought.values())):
            await self._keep(user_id, thread_id, record, {kind: [*brought[kind], *found[kind]] for kind in _KINDS})
        notes: list[tuple[Kind, list[str]]] = [(kind, ids) for kind, ids in found.items() if ids]
        return [note_block(_RULES[kind].note.format(items=_lines(offered[kind], ids))) for kind, ids in notes]

    async def _offered(self, user_id: str) -> dict[Kind, dict[str, str]]:
        """Each kind's memories by id with their lines, but the facts the system prompt holds."""
        saved = await facts.load_all(self._store, user_id)
        held = {f.id for f in facts.in_prompt(saved, settings.memory_basic_facts_tokens)[0]}
        summaries = await episodes.load_all(self._store, user_id)
        return {
            "fact": {f.id: facts.line(f) for f in saved if f.id not in held},
            "episode": {e.id: episodes.line(e) for e in summaries},
        }

    async def _close(
        self, user_id: str, text: str, offered: Mapping[Kind, Mapping[str, str]], shown: Mapping[Kind, set[str]]
    ) -> dict[Kind, list[str]]:
        """Each kind's closest to `text` past its rule, closest first. A failing model only logs: the message goes on
        without them."""
        if not text.strip():
            return _none()
        try:
            scored = await self._recall.scored(user_id, text, _KINDS)
        except EmbeddingError:
            logger.warning("Couldn't find the memories a message touches", exc_info=True)
            return _none()
        return {kind: _picked(_RULES[kind], scored[kind], offered[kind], shown[kind]) for kind in _KINDS}

    async def _keep(
        self, user_id: str, thread_id: str, record: Mapping[Kind, list[str]], added: Mapping[Kind, list[str]]
    ) -> None:
        value = {kind: list(dict.fromkeys([*record[kind], *added[kind]])) for kind in _KINDS}
        await self._store.aput(_namespace(user_id), thread_id, value)


def _none() -> dict[Kind, list[str]]:
    return {kind: [] for kind in _KINDS}


def _picked(rule: _Rule, scored: list[tuple[str, float]], offered: Mapping[str, str], shown: set[str]) -> list[str]:
    if not scored:
        return []
    floor = rule.similarity()
    if rule.margin():
        floor = max(floor, statistics.median(score for _, score in scored) + rule.margin())
    close = [i for i, score in scored if score >= floor and i in offered and i not in shown]
    return close[: rule.most()]


def _lines(offered: Mapping[str, str], ids: list[str]) -> str:
    return "\n".join(offered[i] for i in ids)


def _carried(kind: Kind, offered: Mapping[str, str], notes: list[str]) -> list[str]:
    """The memories of `kind` the notes show, by their lines."""
    return [i for i, line in offered.items() if _shown(kind, line, notes)]


def _shown(kind: Kind, line: str, notes: list[str]) -> bool:
    heading = _RULES[kind].heading
    return any(heading in note and line in note for note in notes)


def _text(content: str | Sequence[Block | str]) -> str:
    """A message's text blocks, its notes among them, as one text."""
    if isinstance(content, str):
        return content
    return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text")


async def _record(store: BaseStore, user_id: str, thread_id: str) -> dict[Kind, list[str]]:
    item = await store.aget(_namespace(user_id), thread_id)
    value = item.value if item else {}
    return {kind: list(value.get(kind, [])) for kind in _KINDS}
