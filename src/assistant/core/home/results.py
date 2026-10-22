"""The last result of each Home section, one Store record each under ("home", user_id, "results"), and when the
last refresh of every section ended, under ("home", user_id). Writing them publishes a `home` event
(core/storage.py), so the apps show each section as soon as it's built."""

from datetime import datetime

from langgraph.store.base import BaseStore

from assistant.core.home.model import SectionResult
from assistant.core.home.sections import namespace

_REFRESHED = "refreshed"
_SCAN_LIMIT = 1000


def _results(user_id: str) -> tuple[str, ...]:
    return (*namespace(user_id), "results")


async def load(store: BaseStore, user_id: str) -> dict[str, SectionResult]:
    """By section id."""
    items = await store.asearch(_results(user_id), limit=_SCAN_LIMIT)
    return {i.key: SectionResult.model_validate(i.value) for i in items}


async def save(store: BaseStore, user_id: str, result: SectionResult) -> None:
    await store.aput(_results(user_id), result.section_id, result.model_dump())


async def forget(store: BaseStore, user_id: str, section_id: str) -> None:
    await store.adelete(_results(user_id), section_id)


async def refreshed_at(store: BaseStore, user_id: str) -> datetime | None:
    item = await store.aget(namespace(user_id), _REFRESHED)
    return datetime.fromisoformat(item.value["at"]) if item else None


async def mark_refreshed(store: BaseStore, user_id: str, at: datetime) -> None:
    await store.aput(namespace(user_id), _REFRESHED, {"at": at.isoformat()})
