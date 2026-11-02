"""The order the apps show the profile's sections in, which the user sets by dragging them (the web app's Settings →
About you). Only how they're shown: the system prompt keeps the profile's own order, so moving a card doesn't start a
new epoch. One Store record per user; a section it doesn't name (one added since) comes after, in the profile's
order."""

from langgraph.store.base import BaseStore

from assistant.core.memory.profile import Profile, Section

_KEY = "order"


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("profile_order", user_id)


async def load(store: BaseStore, user_id: str) -> list[str]:
    """Every section, in the order the user set."""
    sections = list(Profile.model_fields)
    item = await store.aget(_namespace(user_id), _KEY)
    saved = [name for name in (item.value["sections"] if item else []) if name in sections]
    return [*dict.fromkeys(saved), *(name for name in sections if name not in saved)]


async def save(store: BaseStore, user_id: str, sections: list[Section]) -> None:
    await store.aput(_namespace(user_id), _KEY, {"sections": list(dict.fromkeys(sections))})
