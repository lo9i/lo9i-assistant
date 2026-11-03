"""Open loops: what's still to do, waiting on someone, or promised to the user, one Store record each under
("proactive", user_id, "loops"). Archived parts of conversations add them (core/conversation/memory_writer.py), as do
the briefing and the reviews (core/proactive/) and the assistant's tools (core/tools/loops.py); a later conversation
or review that shows one done closes it. A loop is added once per key: one closed or dismissed doesn't come back. The
latest KEPT_CLOSED closed ones are kept for that."""

import re
from datetime import UTC, datetime
from uuid import uuid4

from langgraph.store.base import BaseStore

from assistant.core.config import settings
from assistant.core.jobs.schedule import zone
from assistant.core.memory.items import all_items
from assistant.core.proactive.model import LoopDraft, LoopSource, LoopStatus, OpenLoop, a_kind
from assistant.core.proactive.records import namespace

KEPT_CLOSED = 300
# The open loops a model is shown, at most: the latest.
SHOWN = 40
_KEY_CHARS = 120
_TEXT_CHARS = 300


def _namespace(user_id: str) -> tuple[str, ...]:
    return (*namespace(user_id), "loops")


def key_of(text: str) -> str:
    """What a loop is known by: its words, lowercase."""
    return " ".join(re.findall(r"\w+", text.lower()))[:_KEY_CHARS]


async def all_loops(store: BaseStore, user_id: str) -> list[OpenLoop]:
    """The newest first."""
    loops = [OpenLoop.model_validate(i.value) for i in await all_items(store, _namespace(user_id))]
    return sorted(loops, key=lambda loop: (loop.created_at, loop.id), reverse=True)


async def open_loops(store: BaseStore, user_id: str) -> list[OpenLoop]:
    return [loop for loop in await all_loops(store, user_id) if loop.status == "open"]


async def get(store: BaseStore, user_id: str, loop_id: str) -> OpenLoop | None:
    item = await store.aget(_namespace(user_id), loop_id)
    return OpenLoop.model_validate(item.value) if item else None


async def add(
    store: BaseStore, user_id: str, draft: LoopDraft, source: LoopSource, thread_id: str = ""
) -> OpenLoop | None:
    """None when it's empty, or a loop with its key was added before, whatever became of it."""
    text = " ".join(draft.text.split())[:_TEXT_CHARS]
    key = key_of(draft.key or text)
    if not key or any(loop.key == key for loop in await all_loops(store, user_id)):
        return None
    loop = OpenLoop(
        id=uuid4().hex[:8],
        text=text,
        kind=a_kind(draft.kind),
        source=source,
        thread_id=thread_id,
        created_at=datetime.now(UTC).isoformat(),
        due=draft.due,
        remind_at=_utc(draft.remind_at),
        key=key,
    )
    await _save(store, user_id, loop)
    return loop


async def close(store: BaseStore, user_id: str, loop_id: str, status: LoopStatus) -> OpenLoop | None:
    """Done, dismissed or open again. None for one that isn't there. Past KEPT_CLOSED closed ones, the oldest go."""
    loop = await get(store, user_id, loop_id)
    if loop is None:
        return None
    closed_at = "" if status == "open" else datetime.now(UTC).isoformat()
    changed = loop.model_copy(update={"status": status, "closed_at": closed_at})
    await _save(store, user_id, changed)
    closed = [loop for loop in await all_loops(store, user_id) if loop.status != "open"]
    for old in sorted(closed, key=lambda loop: loop.closed_at, reverse=True)[KEPT_CLOSED:]:
        await store.adelete(_namespace(user_id), old.id)
    return changed


async def due_reminders(store: BaseStore, user_id: str, now: datetime) -> list[OpenLoop]:
    """The open loops whose reminder time came and that weren't reminded of yet, the earliest first."""
    due = [
        loop
        for loop in await open_loops(store, user_id)
        if loop.remind_at and not loop.reminded_at and datetime.fromisoformat(loop.remind_at) <= now
    ]
    return sorted(due, key=lambda loop: loop.remind_at)


async def mark_reminded(store: BaseStore, user_id: str, loop: OpenLoop, now: datetime) -> None:
    await _save(store, user_id, loop.model_copy(update={"reminded_at": now.isoformat()}))


async def forget_conversation(store: BaseStore, user_id: str, thread_id: str) -> None:
    """The conversation was deleted: its loops stay, without the way to open it."""
    for loop in await all_loops(store, user_id):
        if loop.thread_id == thread_id:
            await _save(store, user_id, loop.model_copy(update={"thread_id": ""}))


def render(loops: list[OpenLoop]) -> str:
    """For a model: the latest SHOWN, each with its id."""
    return "\n".join(_line(loop) for loop in loops[:SHOWN]) or "(none)"


def _line(loop: OpenLoop) -> str:
    details = [f"since {loop.created_at[:10]}"]
    details += [f"due {loop.due}"] if loop.due else []
    details += [loop.kind] if loop.kind else []
    return f"- [{loop.id}] {loop.text} ({'; '.join(details)})"


def _utc(local: str) -> str:
    """A moment given in the user's time zone (or with its own), in UTC; "" for none."""
    if not local:
        return ""
    moment = datetime.fromisoformat(local)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone(settings.timezone))
    return moment.astimezone(UTC).isoformat()


async def _save(store: BaseStore, user_id: str, loop: OpenLoop) -> None:
    await store.aput(_namespace(user_id), loop.id, loop.model_dump())
