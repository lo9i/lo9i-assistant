"""Episodes: one summary per finished conversation epoch."""

from dataclasses import dataclass
from uuid import uuid4

from langgraph.store.base import BaseStore

# Search reads at most this many episodes before sorting by date. Beyond it, use search (G2).
_SCAN_LIMIT = 1000


@dataclass
class Episode:
    started_at: str
    ended_at: str
    summary: str


def namespace(user_id: str) -> tuple[str, ...]:
    return ("episodes", user_id)


async def save(store: BaseStore, user_id: str, episode: Episode) -> None:
    value = {"started_at": episode.started_at, "ended_at": episode.ended_at, "summary": episode.summary}
    await store.aput(namespace(user_id), uuid4().hex, value)


async def recent(store: BaseStore, user_id: str, limit: int) -> list[Episode]:
    """The latest `limit` episodes, oldest first."""
    items = await store.asearch(namespace(user_id), limit=_SCAN_LIMIT)
    episodes = sorted((Episode(**i.value) for i in items), key=lambda e: e.ended_at)
    return episodes[-limit:] if limit > 0 else []


def render(episodes: list[Episode]) -> str:
    return "\n".join(f"- {e.started_at[:16]} to {e.ended_at[:16]}: {e.summary}" for e in episodes) or "(none yet)"
