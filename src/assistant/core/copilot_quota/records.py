"""The last check of the allowance, and the alerts sent this period: Store records under ("copilot_quota",)."""

from datetime import datetime

from langgraph.store.base import BaseStore
from pydantic import BaseModel

from assistant.core.copilot_quota.alerts import SentAlerts
from assistant.core.copilot_quota.quota import CopilotQuota

_NAMESPACE = ("copilot_quota",)
_CHECK = "check"
_SENT = "sent"


class Check(BaseModel):
    # When it was checked, ISO 8601.
    at: str
    # The allowance as last read, kept when a later check fails; None until one worked.
    quota: CopilotQuota | None = None
    # Why this check failed; "" when it worked.
    error: str = ""


async def last(store: BaseStore) -> Check | None:
    item = await store.aget(_NAMESPACE, _CHECK)
    return Check.model_validate(item.value) if item else None


async def save_check(store: BaseStore, at: datetime, quota: CopilotQuota | None, error: str = "") -> Check:
    """A failed check (no quota) keeps the allowance read before."""
    before = await last(store)
    check = Check(at=at.isoformat(), quota=quota or (before.quota if before else None), error=error)
    await store.aput(_NAMESPACE, _CHECK, check.model_dump())
    return check


async def sent(store: BaseStore) -> SentAlerts:
    item = await store.aget(_NAMESPACE, _SENT)
    return SentAlerts.model_validate(item.value) if item else SentAlerts()


async def save_sent(store: BaseStore, alerts: SentAlerts) -> None:
    await store.aput(_NAMESPACE, _SENT, alerts.model_dump())
