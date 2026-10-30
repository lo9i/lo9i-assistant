"""The notifications feed: scheduled jobs' results, background work that ended (core/background.py), health checks
and the Copilot allowance's alerts (core/copilot_quota/), listed by the apps apart from any conversation (the web
app's Notifications page, /notifications in the terminal app), newest first, besides the toast or chat message each
one also gets. Each names the
conversation its work was started in, when there is one, so the apps open it from there; a job's run names
its job and run instead, which the apps open on the Jobs page with the run's full reply. One Store record
per notification under ("notifications", user_id); past _KEPT the oldest go."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from langgraph.store.base import BaseStore, PutOp

_KEPT = 200
_SCAN_LIMIT = 10_000

Kind = Literal["job", "background", "doctor", "copilot"]


@dataclass
class Notification:
    id: str
    # ISO 8601.
    at: str
    # job: a scheduled job's run; background: work that ended after the call that started it; doctor: the daily
    # health check (core/doctor/), which the apps open on its page; copilot: the Copilot allowance running low or out
    # (core/copilot_quota/alerts.py), which opens nothing.
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
) -> Notification:
    at = datetime.now(UTC).isoformat()
    notification = Notification(uuid4().hex, at, kind, title, text, ok, thread_id, plugin=plugin)
    await _save(store, user_id, notification)
    return notification


async def add_job_run(store: BaseStore, user_id: str, job: str, run_at: str, text: str, ok: bool) -> Notification:
    """A scheduled job's run, which opens on the Jobs page: its run isn't a conversation the user opens."""
    at = datetime.now(UTC).isoformat()
    notification = Notification(uuid4().hex, at, "job", f"Job {job}", text, ok, job=job, run_at=run_at)
    await _save(store, user_id, notification)
    return notification


async def _save(store: BaseStore, user_id: str, notification: Notification) -> None:
    await store.aput(_namespace(user_id), notification.id, asdict(notification))
    for old in (await recent(store, user_id))[_KEPT:]:
        await store.adelete(_namespace(user_id), old.id)


async def recent(store: BaseStore, user_id: str) -> list[Notification]:
    """Newest first."""
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
    for notification in await recent(store, user_id):
        await store.adelete(_namespace(user_id), notification.id)


async def forget_conversation(store: BaseStore, user_id: str, thread_id: str) -> None:
    """The conversation was deleted: its notifications stay, without the way to open it."""
    for notification in await recent(store, user_id):
        if notification.thread_id == thread_id:
            notification.thread_id = ""
            await store.aput(_namespace(user_id), notification.id, asdict(notification))
