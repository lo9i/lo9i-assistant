from dataclasses import dataclass
from uuid import uuid4

from langgraph.store.base import BaseStore


@dataclass
class Fact:
    id: str
    text: str


def namespace(user_id: str) -> tuple[str, ...]:
    return ("facts", user_id)


async def load(store: BaseStore, user_id: str, limit: int) -> list[Fact]:
    """Up to `limit` facts, sorted by id so the rendered prompt is stable."""
    items = await store.asearch(namespace(user_id), limit=limit)
    return sorted((Fact(id=i.key, text=i.value["fact"]) for i in items), key=lambda f: f.id)


async def add(store: BaseStore, user_id: str, text: str) -> str:
    fact_id = uuid4().hex[:8]
    await store.aput(namespace(user_id), fact_id, {"fact": text})
    return fact_id


async def remove(store: BaseStore, user_id: str, fact_id: str) -> None:
    await store.adelete(namespace(user_id), fact_id)


def render(facts: list[Fact]) -> str:
    return "\n".join(f"- [{f.id}] {f.text}" for f in facts) or "(none yet)"
