"""Episodes: one summary per finished conversation epoch."""

from dataclasses import dataclass
from uuid import uuid4

from langgraph.store.base import BaseStore, Item

from assistant.core.memory.items import all_items


@dataclass
class Episode:
    started_at: str
    ended_at: str
    summary: str
    # The Store key; empty until saved.
    id: str = ""


def namespace(user_id: str) -> tuple[str, ...]:
    return ("episodes", user_id)


async def save(store: BaseStore, user_id: str, episode: Episode) -> None:
    value = {"started_at": episode.started_at, "ended_at": episode.ended_at, "summary": episode.summary}
    await store.aput(namespace(user_id), uuid4().hex, value)


async def recent(store: BaseStore, user_id: str, limit: int) -> list[Episode]:
    """The latest `limit` episodes, oldest first. Older ones are found with search_memory."""
    episodes = sorted(await load_all(store, user_id), key=lambda e: e.ended_at)
    return episodes[-limit:] if limit > 0 else []


async def load_all(store: BaseStore, user_id: str) -> list[Episode]:
    return [_episode(i) for i in await all_items(store, namespace(user_id))]


async def get(store: BaseStore, user_id: str, episode_ids: list[str]) -> list[Episode]:
    """The episodes with these ids that still exist, in the same order."""
    found = [await store.aget(namespace(user_id), episode_id) for episode_id in episode_ids]
    return [_episode(i) for i in found if i is not None]


def _episode(item: Item) -> Episode:
    return Episode(**item.value, id=item.key)


def render(episodes: list[Episode]) -> str:
    return "\n".join(f"- {e.started_at[:16]} to {e.ended_at[:16]}: {e.summary}" for e in episodes) or "(none yet)"
