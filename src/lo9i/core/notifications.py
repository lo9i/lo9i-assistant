"""The notifications feed: only what asks something of the user (NEEDS_USER), the reminders they asked for
(core/proactive/reminders.py) now, listed by the apps apart from any conversation (the web app's Notifications page,
/notifications in the terminal app), newest first. What only informs (scheduled jobs' results, background work that
ended, health checks, the Copilot allowance's and spending limits' alerts, the morning briefing) is offered here by
its code like the rest and left out: it stays in its conversation, on Home, in Alerts and in the toast or chat
message it also gets. Records of those kinds kept from before aren't listed. Each names the conversation its work was
started in, when there is one, so the apps open it from there; a job's run names its job and run instead, which the
apps open on the Jobs page with the run's full reply. One Store record per notification under
("notifications", user_id); past _KEPT the oldest go."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from langgraph.store.base import BaseStore, PutOp

_KEPT = 200
_SCAN_LIMIT = 10_000

Kind = Literal["job", "background", "doctor", "copilot", "spending", "briefing", "reminder"]

# The kinds the feed keeps: those the user has to act on.
NEEDS_USER: frozenset[Kind] = frozenset({"reminder"})


@dataclass
class Notification:
    id: str
    # ISO 8601.
    at: str
    # job: a scheduled job's run; background: work that ended after the call that started it; doctor: the daily
    # health check (core/doctor/), which the apps open on its page; copilot: the Copilot allowance running low or out
    # (core/copilot_quota/alerts.py), which opens nothing; spending: a spending limit nearly reached
    # (core/usage/alerts.py), which opens the conversation for a conversation's limit; briefing: the morning
    # briefing, and reminder: an open loop's reminder (core/proactive/), which opens the loop's conversation when it
    # has one, and Home otherwise (its Open loops card). Only NEEDS_USER's are kept.
    kind: Kind
    title: str
    text: str
    ok: bool
    # The conversation the work was started in, to open it; "" for none (a scheduled job's run).
    thread_id: str = ""
    read: bool = False
    # A job's run: the job's name and when the run started (RunRecord.at), to open it on the Jobs page.
    job: str = ""
    run_at: str = ""
    # The plugin whose work ended, for the apps to show its icon; "" for none.
    plugin: str = ""


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("notifications", user_id)


async def add(
    store: BaseStore, user_id: str, kind: Kind, title: str, text: str, ok: bool, thread_id: str = "", plugin: str = ""
) -> Notification | None:
    """None: the feed doesn't keep its kind."""
    at = datetime.now(UTC).isoformat()
    notification = Notification(uuid4().hex, at, kind, title, text, ok, thread_id, plugin=plugin)
    return await _save(store, user_id, notification)


async def add_job_run(
    store: BaseStore, user_id: str, job: str, run_at: str, text: str, ok: bool
) -> Notification | None:
    """A scheduled job's run, which opens on the Jobs page: its run isn't a conversation the user opens. None: the
    feed doesn't keep it."""
    at = datetime.now(UTC).isoformat()
    notification = Notification(uuid4().hex, at, "job", f"Job {job}", text, ok, job=job, run_at=run_at)
    return await _save(store, user_id, notification)


async def _save(store: BaseStore, user_id: str, notification: Notification) -> Notification | None:
    if notification.kind not in NEEDS_USER:
        return None
    await store.aput(_namespace(user_id), notification.id, asdict(notification))
    for old in (await _every(store, user_id))[_KEPT:]:
        await store.adelete(_namespace(user_id), old.id)
    return notification


async def recent(store: BaseStore, user_id: str) -> list[Notification]:
    """Newest first."""
    return [n for n in await _every(store, user_id) if n.kind in NEEDS_USER]


async def _every(store: BaseStore, user_id: str) -> list[Notification]:
    """Newest first, with those of kinds the feed kept before and doesn't list now."""
    items = await store.asearch(_namespace(user_id), limit=_SCAN_LIMIT)
    return sorted((Notification(**i.value) for i in items), key=lambda n: (n.at, n.id), reverse=True)


async def page(store: BaseStore, user_id: str, offset: int = 0, limit: int | None = None) -> list[Notification]:
    """Newest first, from `offset`: at most `limit`, all of them with None. There are at most _KEPT to sort."""
    return (await recent(store, user_id))[offset : None if limit is None else offset + limit]


async def mark_read(store: BaseStore, user_id: str) -> None:
    """In one write, so clients hear of it once."""
    unread = [n for n in await recent(store, user_id) if not n.read]
    if unread:
        await store.abatch([PutOp(_namespace(user_id), n.id, asdict(n) | {"read": True}) for n in unread])


async def dismiss(store: BaseStore, user_id: str, notification_id: str) -> bool:
    """False for one that isn't there."""
    if await store.aget(_namespace(user_id), notification_id) is None:
        return False
    await store.adelete(_namespace(user_id), notification_id)
    return True


async def clear(store: BaseStore, user_id: str) -> None:
    for notification in await _every(store, user_id):
        await store.adelete(_namespace(user_id), notification.id)


async def forget_conversation(store: BaseStore, user_id: str, thread_id: str) -> None:
    """The conversation was deleted: its notifications stay, without the way to open it."""
    for notification in await recent(store, user_id):
        if notification.thread_id == thread_id:
            notification.thread_id = ""
            await store.aput(_namespace(user_id), notification.id, asdict(notification))
