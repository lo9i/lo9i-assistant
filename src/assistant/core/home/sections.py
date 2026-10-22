"""Home's sections, as the user edited them: one Store record under ("home", user_id), or the built-in ones
until the user saves their own. The built-in instructions are prompt files (home_<id>.md)."""

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


class HomeSectionsError(ValueError):
    """Sections that can't be saved. The text says why."""


def namespace(user_id: str) -> tuple[str, ...]:
    return ("home", user_id)


def built_in() -> list[HomeSection]:
    return [HomeSection(id=i, title=t, prompt=prompts.load(f"home_{i}"), plugins=[p]) for i, t, p in _BUILT_IN]


async def load(store: BaseStore, user_id: str) -> list[HomeSection]:
    item = await store.aget(namespace(user_id), _KEY)
    if item is None:
        return built_in()
    return [HomeSection.model_validate(s) for s in item.value["sections"]]


async def save(store: BaseStore, user_id: str, sections: list[HomeSection]) -> list[HomeSection]:
    """The sections as saved: trimmed, a new one with its id. Raises HomeSectionsError."""
    cleaned = [_cleaned(s) for s in sections]
    _check(cleaned)
    await store.aput(namespace(user_id), _KEY, {"sections": [s.model_dump() for s in cleaned]})
    return cleaned


async def reset(store: BaseStore, user_id: str) -> list[HomeSection]:
    await store.adelete(namespace(user_id), _KEY)
    return built_in()


def _cleaned(section: HomeSection) -> HomeSection:
    plugins = list(dict.fromkeys(p.strip() for p in section.plugins if p.strip()))
    return HomeSection(
        id=section.id.strip() or uuid4().hex[:8],
        title=" ".join(section.title.split()),
        prompt=section.prompt.strip(),
        plugins=plugins,
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
