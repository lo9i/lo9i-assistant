"""Routing from the inbox by meaning, where it's measured to be as good as the model (dispatch.py).

The local embedding model (meanings.py) ranks the conversations a message may continue by how close each is in
meaning; its pick is the closest, scored by that closeness and the margin over the next. Every message routed
from the inbox is logged with that pick, where it was routed, and, for one sent on, the dispatched record its
final place is read from (dispatched.py): a message the user moved later (/move) counts where they moved it.
The logged picks say where the meaning pick agrees with the final place as often as the model's routing did:
the lowest closeness and margin at which it does, over enough picks, is trusted, and a message whose pick
reaches it is routed without a model call. Until enough picks are logged, nothing is trusted and the model
routes every message. One Store record per pick under ("routing_picks", user_id), the latest _KEPT."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from langgraph.store.base import BaseStore

from assistant.core.conversation import dispatched
from assistant.core.conversation.meanings import SimilarConversations

# Picks kept for measuring, the latest first.
_KEPT = 2000
# A band of picks is trusted when at least this many fall in it, the meaning pick agreeing with the final place
# at least this often, and at least as often as the model's routing did there.
MIN_PICKS = 30
MIN_AGREEMENT = 0.95
# The margins over the next conversation a band may ask for.
_MARGINS = (0.0, 0.02, 0.04, 0.06)


@dataclass(frozen=True)
class MeaningPick:
    """The conversation closest in meaning, how close (cosine similarity), and by how much over the next."""

    place: str
    score: float
    margin: float


@dataclass(frozen=True)
class Logged:
    """A logged pick, with where the message ended up: a conversation's id, "" for a new one, or the inbox's own
    places (dispatch.py's QUICK, FOLLOW_UP)."""

    meaning: MeaningPick
    routed: str
    final: str


@dataclass(frozen=True)
class Trust:
    """The picks routed by meaning: those at least this close, by at least this margin; and how often the
    logged picks there agreed, over how many."""

    score: float
    margin: float
    agreement: float
    picks: int

    def covers(self, pick: MeaningPick) -> bool:
        return pick.score >= self.score and pick.margin >= self.margin


async def by_meaning(
    similar: SimilarConversations | None, user_id: str, text: str, candidates: Sequence[str]
) -> MeaningPick | None:
    """The candidate closest in meaning to `text`; None without the index, its model, or candidates."""
    scored = await similar.scored(user_id, text, candidates) if similar else []
    if not scored:
        return None
    (place, score), *rest = scored
    return MeaningPick(place, score, score - rest[0][1] if rest else score)


async def log(store: BaseStore, user_id: str, pick: MeaningPick, routed: str, candidates: Sequence[str]) -> str:
    """Logs a message's pick and where it was routed; returns the pick's id, which `sent_on` ties to the
    dispatched record of a message sent on."""
    pick_id = uuid4().hex
    value = {
        "at": datetime.now(UTC).isoformat(),
        "place": pick.place,
        "score": pick.score,
        "margin": pick.margin,
        "routed": routed,
        "candidates": list(candidates),
        "dispatch_id": "",
    }
    await store.aput(_namespace(user_id), pick_id, value)
    return pick_id


async def sent_on(store: BaseStore, user_id: str, pick_id: str, dispatch_id: str) -> None:
    """The message of the pick was sent on as `dispatch_id`: its final place is that record's."""
    item = await store.aget(_namespace(user_id), pick_id)
    if item is not None:
        await store.aput(_namespace(user_id), pick_id, item.value | {"dispatch_id": dispatch_id})


async def trusted(store: BaseStore, user_id: str) -> Trust | None:
    """The band the logged picks trust; None while none is."""
    return calibrate(await logged(store, user_id))


async def logged(store: BaseStore, user_id: str) -> list[Logged]:
    """The logged picks, the latest first, each with its final place. The oldest beyond _KEPT are forgotten."""
    items = sorted(await store.asearch(_namespace(user_id), limit=10_000), key=lambda i: i.value["at"], reverse=True)
    for item in items[_KEPT:]:
        await store.adelete(_namespace(user_id), item.key)
    sent = await dispatched.places(store, user_id)
    return [
        Logged(MeaningPick(v["place"], v["score"], v["margin"]), v["routed"], _final(v, sent))
        for v in (item.value for item in items[:_KEPT])
    ]


def calibrate(picks: Sequence[Logged]) -> Trust | None:
    """The band with the most picks where the meaning pick agrees with the final place at least MIN_AGREEMENT of
    the time and at least as often as the routing did, over at least MIN_PICKS picks; None when no band does."""
    best: Trust | None = None
    for margin in _MARGINS:
        wide = sorted((p for p in picks if p.meaning.margin >= margin), key=lambda p: p.meaning.score, reverse=True)
        agreed = routed = 0
        for count, pick in enumerate(wide, 1):
            agreed += pick.meaning.place == pick.final
            routed += pick.routed == pick.final
            # A band ends between two scores, so one that ties the next isn't split.
            if count < len(wide) and wide[count].meaning.score == pick.meaning.score:
                continue
            agreement = agreed / count
            good = count >= MIN_PICKS and agreement >= MIN_AGREEMENT and agreed >= routed
            if good and (best is None or count > best.picks):
                best = Trust(pick.meaning.score, margin, agreement, count)
    return best


def _final(value: dict, sent: dict[str, str]) -> str:
    """Where the message ended up: where it was routed, or, sent on, the conversation it's in now (`sent`, by
    dispatch id), "" when that wasn't one it could have continued (a new one)."""
    if value["dispatch_id"] not in sent:
        return value["routed"]
    now = sent[value["dispatch_id"]]
    if not now:
        return value["routed"]  # Kept, not sent on yet.
    return now if now in value["candidates"] else ""


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("routing_picks", user_id)
