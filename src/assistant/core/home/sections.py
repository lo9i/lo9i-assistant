"""Home's sections, as the user edited them: one Store record under ("home", user_id), or the built-in ones
until the user saves their own. The built-in instructions are prompt files (home_<id>.md). Sections built by code
(coded.py) are built in too; one added after the user saved their own is added to theirs, and stays away once
they remove it, since the record says which ones they had when they saved."""

from uuid import uuid4

from langgraph.store.base import BaseStore

from assistant.core import i18n
from assistant.core.conversation import prompts
from assistant.core.home.model import HomeSection
from assistant.core.i18n import Texts, said, translatable

MAX_SECTIONS = 12
_KEY = "sections"
# Built in: id, title and the plugin each reads. Their titles and what the coded ones show are in the language
# chosen until the user saves the sections, which keeps them as they were then.
_BUILT_IN = (
    ("calendar", translatable("Calendar"), "calendar"),
    ("watchlist", translatable("Watchlist"), "watchlist"),
    ("expenses", translatable("Expenses"), "expenses"),
)
COPILOT = "copilot"
CONVERSATIONS = "conversations"
# Built in and built by code: id, title, and what the apps show as what it shows (no model reads it), which only
# the code changes.
_CODED = (
    (
        COPILOT,
        translatable("Copilot"),
        translatable(
            "Built by lo9i from what GitHub reports, without the model: the Copilot plan, the premium requests left, "
            "the credits used and when they reset."
        ),
    ),
    (
        CONVERSATIONS,
        translatable("Conversations"),
        translatable(
            "Built by lo9i, without the model: the conversations pinned to Home (Pin to Home in Chat), or the most "
            "recent ones while none is, each with its latest message and whether it's working or waiting for you."
        ),
    ),
)


class HomeSectionsError(ValueError):
    """Sections that can't be saved. The text says why."""


def namespace(user_id: str) -> tuple[str, ...]:
    return ("home", user_id)


def built_in(t: Texts) -> list[HomeSection]:
    by_model = [
        HomeSection(id=i, title=t(title), prompt=prompts.load(f"home_{i}"), plugins=[p]) for i, title, p in _BUILT_IN
    ]
    return by_model + _coded(t)


async def load(store: BaseStore, user_id: str) -> list[HomeSection]:
    item, t = await store.aget(namespace(user_id), _KEY), await i18n.chosen(store)
    if item is None:
        return built_in(t)
    saved = [_as_coded(HomeSection.model_validate(s), t) for s in item.value["sections"]]
    return saved + _coded_since(item.value.get("coded", []), saved, t)


async def save(store: BaseStore, user_id: str, sections: list[HomeSection]) -> list[HomeSection]:
    """The sections as saved: trimmed, a new one with its id. Raises HomeSectionsError."""
    t = await i18n.chosen(store)
    cleaned = [_cleaned(s, t) for s in sections]
    _check(cleaned)
    record = {"sections": [s.model_dump() for s in cleaned], "coded": [i for i, _, _ in _CODED]}
    await store.aput(namespace(user_id), _KEY, record)
    return cleaned


async def reset(store: BaseStore, user_id: str) -> list[HomeSection]:
    await store.adelete(namespace(user_id), _KEY)
    return built_in(await i18n.chosen(store))


def _coded(t: Texts) -> list[HomeSection]:
    return [HomeSection(id=i, title=t(title), prompt=t(shows), coded=True) for i, title, shows in _CODED]


def _as_coded(section: HomeSection, t: Texts) -> HomeSection:
    """A saved section built by code says so, with what it shows as the code says now; any other as it was saved."""
    coded = {s.id: s for s in _coded(t)}.get(section.id)
    return section.model_copy(update={"prompt": coded.prompt, "plugins": [], "coded": True}) if coded else section


def _coded_since(known: list[str], saved: list[HomeSection], t: Texts) -> list[HomeSection]:
    """The sections built by code that came after the user's were saved."""
    skip = {*known, *(s.id for s in saved)}
    return [s for s in _coded(t) if s.id not in skip]


def _cleaned(section: HomeSection, t: Texts) -> HomeSection:
    """A section built by code keeps its own text whatever the app sends, so an app adds one back by its id; only its
    title and width are the app's."""
    plugins = list(dict.fromkeys(p.strip() for p in section.plugins if p.strip()))
    cleaned = HomeSection(
        id=section.id.strip() or uuid4().hex[:8],
        title=" ".join(section.title.split()),
        prompt=section.prompt.strip(),
        plugins=plugins,
        columns=section.columns,
    )
    return _as_coded(cleaned, t)


def _check(sections: list[HomeSection]) -> None:
    if len(sections) > MAX_SECTIONS:
        raise HomeSectionsError(said("Home has room for {count} sections.", count=MAX_SECTIONS))
    if len({s.id for s in sections}) < len(sections):
        raise HomeSectionsError(said("Two sections have the same id."))
    for section in sections:
        if not section.title:
            raise HomeSectionsError(said("Every section needs a title."))
        if not section.prompt:
            raise HomeSectionsError(said("Say what {title} shows.", title=section.title))
