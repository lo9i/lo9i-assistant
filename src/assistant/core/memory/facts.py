from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from langgraph.store.base import BaseStore, Item

from assistant.core.memory.items import all_items


@dataclass
class Fact:
    id: str
    text: str
    # When it was saved, in UTC without a zone like the Store's times; "" for one not read from the Store.
    saved_at: str = ""


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
    return Fact(id=item.key, text=item.value["fact"], saved_at=_saved_at(item).isoformat())


async def add(store: BaseStore, user_id: str, text: str) -> str:
    fact_id = uuid4().hex[:8]
    saved_at = datetime.now(UTC).replace(tzinfo=None).isoformat()
    await store.aput(namespace(user_id), fact_id, {"fact": text, "saved_at": saved_at})
    return fact_id


async def remove(store: BaseStore, user_id: str, fact_id: str) -> None:
    await store.adelete(namespace(user_id), fact_id)


async def replace(store: BaseStore, user_id: str, fact_id: str, text: str) -> Fact | None:
    """Saves the new text under a new id, keeping when it was saved, and deletes the old one: the search
    index (indexer.py) embeds what has a new key, so the vector follows the text. None when it's gone."""
    item = await store.aget(namespace(user_id), fact_id)
    if item is None:
        return None
    new_id = uuid4().hex[:8]
    await store.aput(namespace(user_id), new_id, {"fact": text, "saved_at": _saved_at(item).isoformat()})
    await remove(store, user_id, fact_id)
    return Fact(new_id, text, _saved_at(item).isoformat())


def render(facts: list[Fact]) -> str:
    return "\n".join(f"- [{f.id}] {f.text}" for f in facts) or "(none yet)"
