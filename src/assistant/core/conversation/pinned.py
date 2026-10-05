"""Skills the user pinned to a conversation. Their instructions go in the system prompt of every epoch
(core/conversation/prompt.py), so they hold for the whole conversation instead of fading like a
use_skill result, which is trimmed and summarized away. A change starts a new epoch at the next user
message, and that message's turn header says what changed, once."""

from typing import Any

from langgraph.store.base import BaseStore

from assistant.core.conversation import prompts
from assistant.core.conversation.turn_header import note_block


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("pinned_skills", user_id)


async def load(store: BaseStore, user_id: str, thread_id: str) -> list[str]:
    """The pinned skills' names, in the order they were pinned."""
    return list((await _record(store, user_id, thread_id)).get("skills", []))


async def pin(store: BaseStore, user_id: str, thread_id: str, name: str) -> list[str]:
    current = await load(store, user_id, thread_id)
    if name in current:
        return current
    return await _save(store, user_id, thread_id, [*current, name])


async def unpin(store: BaseStore, user_id: str, thread_id: str, name: str) -> list[str]:
    current = await load(store, user_id, thread_id)
    if name not in current:
        return current
    return await _save(store, user_id, thread_id, [s for s in current if s != name])


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """For a deleted conversation."""
    await store.adelete(_namespace(user_id), thread_id)


async def take_notice(store: BaseStore, user_id: str, thread_id: str) -> list[dict[str, str]]:
    """The turn header note after a change, or nothing. It's cleared: it goes into one message only."""
    record = await _record(store, user_id, thread_id)
    if not record.get("changed"):
        return []
    skills = record.get("skills", [])
    await store.aput(_namespace(user_id), thread_id, {"skills": skills, "changed": False})
    return [note_block(prompts.load("pinned_changed").format(pinned=", ".join(skills) or "none"))]


async def _record(store: BaseStore, user_id: str, thread_id: str) -> dict[str, Any]:
    item = await store.aget(_namespace(user_id), thread_id)
    return item.value if item else {}


async def _save(store: BaseStore, user_id: str, thread_id: str, skills: list[str]) -> list[str]:
    await store.aput(_namespace(user_id), thread_id, {"skills": skills, "changed": True})
    return skills
