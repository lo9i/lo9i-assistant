"""The proactive records, under ("proactive", user_id): the settings, the latest briefing and how many reminders went
each day; the reviews under ("proactive", user_id, "reviews"), the latest KEPT_REVIEWS. Writing them publishes a
`proactive` event (core/storage.py)."""

from langgraph.store.base import BaseStore

from lo9i.core.proactive.model import MAX_MUTED, Briefing, ProactiveSettings, Review, a_kind

KEPT_REVIEWS = 30
_SETTINGS = "settings"
_BRIEFING = "briefing"
_REMINDED = "reminded"
_SCAN_LIMIT = 1000


def namespace(user_id: str) -> tuple[str, ...]:
    return ("proactive", user_id)


def _reviews(user_id: str) -> tuple[str, ...]:
    return (*namespace(user_id), "reviews")


async def load_settings(store: BaseStore, user_id: str) -> ProactiveSettings:
    item = await store.aget(namespace(user_id), _SETTINGS)
    return ProactiveSettings.model_validate(item.value) if item else ProactiveSettings()


async def save_settings(store: BaseStore, user_id: str, wanted: ProactiveSettings) -> ProactiveSettings:
    await store.aput(namespace(user_id), _SETTINGS, wanted.model_dump())
    return wanted


async def mute(store: BaseStore, user_id: str, kind: str, muted: bool = True) -> ProactiveSettings:
    """Stops (or, with `muted` false, starts again) suggesting that kind of thing. Past MAX_MUTED, the oldest muted
    kind is given up."""
    current = await load_settings(store, user_id)
    kinds = [k for k in current.muted if k != a_kind(kind)] + ([kind] if muted else [])
    wanted = ProactiveSettings.model_validate({**current.model_dump(), "muted": kinds[-MAX_MUTED:]})
    return await save_settings(store, user_id, wanted)


async def latest_briefing(store: BaseStore, user_id: str) -> Briefing | None:
    item = await store.aget(namespace(user_id), _BRIEFING)
    return Briefing.model_validate(item.value) if item else None


async def save_briefing(store: BaseStore, user_id: str, briefing: Briefing) -> None:
    await store.aput(namespace(user_id), _BRIEFING, briefing.model_dump())


async def reviews(store: BaseStore, user_id: str) -> list[Review]:
    """The latest first."""
    items = await store.asearch(_reviews(user_id), limit=_SCAN_LIMIT)
    return sorted((Review.model_validate(i.value) for i in items), key=lambda r: r.at, reverse=True)


async def save_review(store: BaseStore, user_id: str, review: Review) -> None:
    await store.aput(_reviews(user_id), _key(review), review.model_dump())
    for old in (await reviews(store, user_id))[KEPT_REVIEWS:]:
        await store.adelete(_reviews(user_id), _key(old))


async def mark_briefed(store: BaseStore, user_id: str, briefed: list[Review]) -> None:
    for review in briefed:
        await store.aput(_reviews(user_id), _key(review), review.model_copy(update={"briefed": True}).model_dump())


async def reminded_on(store: BaseStore, user_id: str, day: str) -> int:
    """How many reminders went on that day."""
    item = await store.aget(namespace(user_id), _REMINDED)
    return int(item.value.get("count", 0)) if item and item.value.get("day") == day else 0


async def count_reminder(store: BaseStore, user_id: str, day: str) -> None:
    await store.aput(namespace(user_id), _REMINDED, {"day": day, "count": await reminded_on(store, user_id, day) + 1})


def _key(review: Review) -> str:
    return f"{review.day}:{review.kind}"
