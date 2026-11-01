"""Which spending limits nearly reached were told already (budget.py), so each is told once per limit and period: one
Store record per limit, period and amount, kept _KEPT_DAYS, past any day or job run; a conversation still spending
toward its limit after that is told again."""

from datetime import UTC, datetime, timedelta

from langgraph.store.base import BaseStore

_NAMESPACE = ("spending_warned",)
_KEPT_DAYS = 30
_LISTED = 10_000


async def first(store: BaseStore, key: str, now: datetime | None = None) -> bool:
    """Records `key` as told; whether it wasn't before. Forgets those past _KEPT_DAYS."""
    if await store.aget(_NAMESPACE, key) is not None:
        return False
    at = now or datetime.now(UTC)
    await store.aput(_NAMESPACE, key, {"at": at.isoformat()})
    await _forget_before(store, at - timedelta(days=_KEPT_DAYS))
    return True


async def _forget_before(store: BaseStore, when: datetime) -> None:
    for item in await store.asearch(_NAMESPACE, limit=_LISTED):
        if datetime.fromisoformat(item.value["at"]) < when:
            await store.adelete(_NAMESPACE, item.key)
