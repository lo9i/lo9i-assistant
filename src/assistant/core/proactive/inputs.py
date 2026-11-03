"""What the briefing and the reviews read besides their sources: the habits the reviews saved, the language to write
in, and the kinds of suggestion the user muted.

Habits are saved facts (core/memory/facts.py) starting with HABIT, as the About you answers are profile items starting
with their label: they're memory like any fact (search_memory finds them, the system prompt lists the recent ones,
the user edits them in Memory), and the briefing and reviews read them back by that start."""

from langgraph.store.base import BaseStore

from assistant.core import i18n
from assistant.core.memory import about_you, facts, profile
from assistant.core.proactive.loops import key_of
from assistant.core.proactive.model import ProactiveSettings

HABIT = "Habit: "
_LANGUAGES = {"en": "English", "es": "Spanish"}


async def habits(store: BaseStore, user_id: str) -> list[str]:
    return [f.text.removeprefix(HABIT) for f in await facts.load_all(store, user_id) if f.text.startswith(HABIT)]


async def save_habits(store: BaseStore, user_id: str, found: list[str]) -> list[str]:
    """Saves those not saved yet; returns them."""
    known = {key_of(h) for h in await habits(store, user_id)}
    saved: list[str] = []
    for text in (" ".join(h.split()) for h in found):
        if text and key_of(text) not in known:
            await facts.add(store, user_id, f"{HABIT}{text}")
            known.add(key_of(text))
            saved.append(text)
    return saved


async def language(store: BaseStore, user_id: str) -> str:
    """The language the user asked replies in (About you), else the one the apps show."""
    asked = about_you.read(await profile.load(store, user_id)).language
    return asked or _LANGUAGES[(await i18n.chosen(store)).language]


def listed(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines) or "(none)"


def muted(chosen: ProactiveSettings) -> str:
    return ", ".join(chosen.muted) or "(none)"
