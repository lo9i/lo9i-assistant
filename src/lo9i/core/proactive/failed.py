"""The briefing's and the reviews' failures, as alerts (core/agent/alerts.py): the latest briefing, and the latest
review of each kind, when it failed and the user didn't dismiss it. The next one that works clears it, being the
latest then. The web app shows nothing else of them, so this is how a failure is seen."""

from dataclasses import dataclass

from langgraph.store.base import BaseStore

from lo9i.core.proactive import records
from lo9i.core.proactive.model import Review


@dataclass
class Failed:
    # briefing, nightly or weekly.
    work: str
    error: str
    # When it ran (ISO 8601).
    at: str


async def failed(store: BaseStore, user_id: str) -> list[Failed]:
    found = []
    briefing = await records.latest_briefing(store, user_id)
    if briefing and briefing.status == "failed" and not briefing.dismissed:
        found.append(Failed("briefing", briefing.error, briefing.at))
    latest = (await _latest_reviews(store, user_id)).values()
    return found + [Failed(r.kind, r.error, r.at) for r in latest if r.error and not r.dismissed]


async def dismiss(store: BaseStore, user_id: str, work: str) -> None:
    """Its latest run's failure stops being an alert. Nothing for one that never ran."""
    if work == "briefing":
        if (briefing := await records.latest_briefing(store, user_id)) is not None:
            await records.save_briefing(store, user_id, briefing.model_copy(update={"dismissed": True}))
    elif (review := (await _latest_reviews(store, user_id)).get(work)) is not None:
        await records.save_review(store, user_id, review.model_copy(update={"dismissed": True}))


async def _latest_reviews(store: BaseStore, user_id: str) -> dict[str, Review]:
    """The latest review of each kind."""
    latest: dict[str, Review] = {}
    for review in await records.reviews(store, user_id):
        latest.setdefault(review.kind, review)
    return latest
