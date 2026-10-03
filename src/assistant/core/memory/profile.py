"""The user profile: one structured document per user, a few short lists the system prompt shows."""

from typing import Literal

from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field

from assistant.core.memory import facts

Section = Literal["about", "people", "how_to_reply", "routine", "goals", "interests", "dislikes", "work"]

# Every item is in every system prompt, so each section stays short. A full section gets items
# replaced or merged, not appended.
MAX_ITEMS = 8

_KEY = "profile"
_NAMESPACE_ROOT = "profile"
# Sections before the current set, and where their items went.
_OLD_SECTIONS = {
    "wants": "goals",
    "likes": "interests",
    "interests": "interests",
    "dislikes": "dislikes",
    "projects": "work",
    "work": "work",
    "technical_level": "work",
}


def _section(description: str) -> list[str]:
    return Field(default_factory=list, max_length=MAX_ITEMS, description=f"{description} At most {MAX_ITEMS} items.")


class Profile(BaseModel):
    about: list[str] = _section("Who the user is: name, where they live and their timezone, languages.")
    people: list[str] = _section("People in the user's life and how they relate, e.g. 'Ana: sister'.")
    how_to_reply: list[str] = _section(
        "How the user wants replies: length, tone, format, language, and what to include when they ask for something "
        "in particular, e.g. 'unpaid bills: list each with its obligation's details'."
    )
    routine: list[str] = _section("The user's schedule and habits: working hours, regular commitments.")
    goals: list[str] = _section(
        "Outcomes the user is working toward over weeks or months, e.g. 'learn Italian', 'save for a trip'. Never "
        "requests or instructions about replies: those go in how_to_reply."
    )
    interests: list[str] = _section("Topics and things the user likes.")
    dislikes: list[str] = _section("Things the user dislikes or wants avoided.")
    work: list[str] = _section("The user's work: role, field, tools, projects, technical level.")


def namespace(user_id: str) -> tuple[str, ...]:
    return (_NAMESPACE_ROOT, user_id)


async def load(store: BaseStore, user_id: str) -> Profile:
    item = await store.aget(namespace(user_id), _KEY)
    return Profile.model_validate(item.value) if item else Profile()


async def save(store: BaseStore, user_id: str, profile: Profile) -> None:
    await store.aput(namespace(user_id), _KEY, profile.model_dump())


def render(profile: Profile) -> str:
    lines = [f"- {_title(name)}: {'; '.join(items)}" for name, items in profile.model_dump().items() if items]
    return "\n".join(lines) or "(empty so far)"


def _title(section: str) -> str:
    return section.replace("_", " ").capitalize()


async def migrate(store: BaseStore) -> None:
    """Moves profiles saved with the old sections into the current ones."""
    for space in await store.alist_namespaces(prefix=(_NAMESPACE_ROOT,)):
        item = await store.aget(space, _KEY)
        if item is not None and set(item.value) - set(Profile.model_fields):
            await _migrate_one(store, space[-1], item.value)


async def _migrate_one(store: BaseStore, user_id: str, old: dict[str, list[str]]) -> None:
    """Items beyond a section's limit become facts, so nothing is lost."""
    merged: dict[str, list[str]] = {}
    for name, items in old.items():
        target = _OLD_SECTIONS.get(name, name)
        merged[target] = list(dict.fromkeys([*merged.get(target, []), *items]))
    for items in merged.values():
        for text in items[MAX_ITEMS:]:
            await facts.add(store, user_id, text)
    await save(store, user_id, Profile(**{name: items[:MAX_ITEMS] for name, items in merged.items()}))
