"""The notifications feed: scheduled jobs' results and background work that ended (core/background.py),
listed by the apps apart from any conversation (the web app's Notifications page, /notifications in the
terminal app), newest first, besides the toast or chat message each one also gets. Each names the
conversation its work was started in, when there is one, so the apps open it from there. One Store record
per notification under ("notifications", user_id); past _KEPT the oldest go."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from langgraph.store.base import BaseStore, PutOp

_KEPT = 200
_SCAN_LIMIT = 10_000

Kind = Literal["job", "background"]


@dataclass
class Notification:
    id: str
    # ISO 8601.
    at: str
    # job: a scheduled job's run; background: work that ended after the call that started it.
    kind: Kind
    title: str
    text: str
    ok: bool
    # The conversation the work was started in, to open it; "" for none (a scheduled job's run).
    thread_id: str = ""
    read: bool = False


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("notifications", user_id)


async def add(
    store: BaseStore, user_id: str, kind: Kind, title: str, text: str, ok: bool, thread_id: str = ""
) -> Notification:
    notification = Notification(uuid4().hex, datetime.now(UTC).isoformat(), kind, title, text, ok, thread_id)
    await store.aput(_namespace(user_id), notification.id, asdict(notification))
    for old in (await recent(store, user_id))[_KEPT:]:
        await store.adelete(_namespace(user_id), old.id)
    return notification


async def recent(store: BaseStore, user_id: str) -> list[Notification]:
    """Newest first."""
    items = await store.asearch(_namespace(user_id), limit=_SCAN_LIMIT)
    return sorted((Notification(**i.value) for i in items), key=lambda n: n.at, reverse=True)


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
