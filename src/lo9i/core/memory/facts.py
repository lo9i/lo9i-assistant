"""Saved facts: details about the user that stay true. A basic one goes in every system prompt (core/conversation/
prompt.py), within a budget of tokens; the others come into a turn when a message is close to them in meaning
(core/conversation/relevant_facts.py), and search_memory finds them all."""

from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import replace as replaced
from datetime import UTC, datetime
from uuid import uuid4

from langgraph.store.base import BaseStore, Item

from lo9i.core.memory.items import all_items
from lo9i.core.usage.tokens import estimate_text

# A basic fact is one short line: every conversation carries it.
BASIC_MAX_CHARS = 160


@dataclass
class Fact:
    id: str
    text: str
    # When it was saved, in UTC without a zone like the Store's times; "" for one not read from the Store.
    saved_at: str = ""
    # In every system prompt, instead of coming in when a message touches it.
    basic: bool = False


def namespace(user_id: str) -> tuple[str, ...]:
    return ("facts", user_id)


async def load(store: BaseStore, user_id: str, limit: int) -> list[Fact]:
    """The `limit` most recently saved facts, sorted by id so the rendered prompt is stable.
    Older ones are found with search_memory."""
    items = sorted(await all_items(store, namespace(user_id)), key=_saved_at, reverse=True)
    return sorted((_fact(i) for i in items[: max(limit, 0)]), key=lambda f: f.id)


async def load_all(store: BaseStore, user_id: str) -> list[Fact]:
    return [_fact(i) for i in await all_items(store, namespace(user_id))]


async def get(store: BaseStore, user_id: str, fact_ids: list[str]) -> list[Fact]:
    """The facts with these ids that still exist, in the same order."""
    found = [await store.aget(namespace(user_id), fact_id) for fact_id in fact_ids]
    return [_fact(i) for i in found if i is not None]


def _saved_at(item: Item) -> datetime:
    """In UTC, without a zone, like the Store's times. The Store keeps whole seconds, which can't
    order the facts one digest saves; facts saved before `saved_at` existed fall back to it."""
    saved_at = item.value.get("saved_at")
    return datetime.fromisoformat(saved_at) if saved_at else item.updated_at


def _fact(item: Item) -> Fact:
    basic = bool(item.value.get("basic", False))
    return Fact(id=item.key, text=item.value["fact"], saved_at=_saved_at(item).isoformat(), basic=basic)


def _value(fact: Fact) -> dict[str, object]:
    return {"fact": fact.text, "saved_at": fact.saved_at, "basic": fact.basic}


async def add(store: BaseStore, user_id: str, text: str, basic: bool = False) -> str:
    fact_id = uuid4().hex[:8]
    saved_at = datetime.now(UTC).replace(tzinfo=None).isoformat()
    await store.aput(namespace(user_id), fact_id, _value(Fact(fact_id, text, saved_at, basic)))
    return fact_id


async def remove(store: BaseStore, user_id: str, fact_id: str) -> None:
    await store.adelete(namespace(user_id), fact_id)


async def replace(store: BaseStore, user_id: str, fact_id: str, text: str) -> Fact | None:
    """Saves the new text under a new id, keeping when it was saved, and deletes the old one: the search
    index (indexer.py) embeds what has a new key, so the vector follows the text. None when it's gone."""
    item = await store.aget(namespace(user_id), fact_id)
    if item is None:
        return None
    edited = replaced(_fact(item), id=uuid4().hex[:8], text=text)
    await store.aput(namespace(user_id), edited.id, _value(edited))
    await remove(store, user_id, fact_id)
    return edited


async def set_basic(store: BaseStore, user_id: str, fact_id: str, basic: bool) -> Fact | None:
    """Under the same id: the text, and so its vector, stays. None when it's gone."""
    item = await store.aget(namespace(user_id), fact_id)
    if item is None:
        return None
    changed = replaced(_fact(item), basic=basic)
    await store.aput(namespace(user_id), fact_id, _value(changed))
    return changed


def too_long_for_basic(text: str) -> bool:
    return "\n" in text.strip() or len(text.strip()) > BASIC_MAX_CHARS


def in_prompt(saved: Sequence[Fact], budget: int) -> tuple[list[Fact], list[Fact]]:
    """The basic facts the system prompt holds, newest first until `budget` tokens, sorted by id so the prompt is
    stable; and the basic ones past the budget, left out."""
    kept: list[Fact] = []
    left_out: list[Fact] = []
    used = 0
    for fact in sorted((f for f in saved if f.basic), key=lambda f: f.saved_at, reverse=True):
        cost = estimate_text(line(fact) + "\n")
        if used + cost <= budget:
            kept.append(fact)
            used += cost
        else:
            left_out.append(fact)
    return sorted(kept, key=lambda f: f.id), left_out


def render(facts: list[Fact]) -> str:
    return "\n".join(line(f) for f in facts) or "(none yet)"


def line(fact: Fact) -> str:
    """A fact's line in the system prompt."""
    return f"- [{fact.id}] {fact.text}"
