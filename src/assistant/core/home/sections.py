"""Home's sections, as the user edited them: one Store record under ("home", user_id), or the built-in ones
until the user saves their own. The built-in instructions are prompt files (home_<id>.md). Sections built by code
(coded.py) are built in too; one added after the user saved their own is added to theirs, and stays away once
they remove it, since the record says which ones they had when they saved."""

from uuid import uuid4

from langgraph.store.base import BaseStore

from assistant.core.conversation import prompts
from assistant.core.home.model import HomeSection

MAX_SECTIONS = 12
_KEY = "sections"
# Built in: id, title and the plugin each reads.
_BUILT_IN = (
    ("calendar", "Calendario", "calendar"),
    ("watchlist", "Watchlist", "watchlist"),
    ("expenses", "Gastos", "expenses"),
)
COPILOT = "copilot"
# Built in and built by code: id, title, and what the editor shows as what it shows (no model reads it).
_CODED = (
    (
        COPILOT,
        "Copilot",
        "Built by lo9i from what GitHub reports, without the model: the Copilot plan, the premium requests left, "
        "the credits used and when they reset. Changing this text changes nothing.",
    ),
)


class HomeSectionsError(ValueError):
    """Sections that can't be saved. The text says why."""


def namespace(user_id: str) -> tuple[str, ...]:
    return ("home", user_id)


def built_in() -> list[HomeSection]:
    by_model = [HomeSection(id=i, title=t, prompt=prompts.load(f"home_{i}"), plugins=[p]) for i, t, p in _BUILT_IN]
    return by_model + _coded()


async def load(store: BaseStore, user_id: str) -> list[HomeSection]:
    item = await store.aget(namespace(user_id), _KEY)
    if item is None:
        return built_in()
    saved = [HomeSection.model_validate(s) for s in item.value["sections"]]
    return saved + _coded_since(item.value.get("coded", []), saved)


async def save(store: BaseStore, user_id: str, sections: list[HomeSection]) -> list[HomeSection]:
    """The sections as saved: trimmed, a new one with its id. Raises HomeSectionsError."""
    cleaned = [_cleaned(s) for s in sections]
    _check(cleaned)
    record = {"sections": [s.model_dump() for s in cleaned], "coded": [s.id for s in _coded()]}
    await store.aput(namespace(user_id), _KEY, record)
    return cleaned


async def reset(store: BaseStore, user_id: str) -> list[HomeSection]:
    await store.adelete(namespace(user_id), _KEY)
    return built_in()


def _coded() -> list[HomeSection]:
    return [HomeSection(id=i, title=t, prompt=p) for i, t, p in _CODED]


def _coded_since(known: list[str], saved: list[HomeSection]) -> list[HomeSection]:
    """The sections built by code that came after the user's were saved."""
    skip = {*known, *(s.id for s in saved)}
    return [s for s in _coded() if s.id not in skip]


def _cleaned(section: HomeSection) -> HomeSection:
    plugins = list(dict.fromkeys(p.strip() for p in section.plugins if p.strip()))
    return HomeSection(
        id=section.id.strip() or uuid4().hex[:8],
        title=" ".join(section.title.split()),
        prompt=section.prompt.strip(),
        plugins=plugins,
        columns=section.columns,
    )


def _check(sections: list[HomeSection]) -> None:
    if len(sections) > MAX_SECTIONS:
        raise HomeSectionsError(f"Home has room for {MAX_SECTIONS} sections.")
    if len({s.id for s in sections}) < len(sections):
        raise HomeSectionsError("Two sections have the same id.")
    for section in sections:
        if not section.title:
            raise HomeSectionsError("Every section needs a title.")
        if not section.prompt:
            raise HomeSectionsError(f"Say what {section.title} shows.")
