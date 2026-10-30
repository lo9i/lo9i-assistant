"""Routing from the inbox by meaning where it's measured to be as good as the model (routing_picks.py): every pick is
logged with where its message ended up, and the band of closeness the logged picks trust routes without a model
call. The embedder is the fake one (tests/conftest.py), whose vectors come from the words."""

from assistant.core import conversations
from assistant.core.agent import AssistantService, Session
from assistant.core.conversation import routing_picks
from assistant.core.conversation.dispatch import QUICK, Pick
from assistant.core.conversation.routing_picks import MIN_PICKS, Logged, MeaningPick, Trust, calibrate
from assistant.core.conversations import Conversation
from assistant.core.events import Dispatched
from tests.conftest import collect


def _picks(n: int, score: float, agrees: bool = True, routed_agrees: bool = True, margin: float = 0.1) -> list[Logged]:
    final = "t1" if agrees else "t2"
    return [Logged(MeaningPick("t1", score, margin), final if routed_agrees else "t3", final) for _ in range(n)]


def test_nothing_is_trusted_before_enough_picks():
    assert calibrate(_picks(MIN_PICKS - 1, 0.9)) is None
    assert calibrate(_picks(MIN_PICKS, 0.9)) == Trust(0.9, 0.0, 1.0, MIN_PICKS)


def test_the_widest_band_that_agrees_often_enough_is_trusted():
    # Close ones agree; below 0.8 they often don't, so the band stops there.
    picks = _picks(40, 0.9) + _picks(10, 0.8) + _picks(30, 0.7, agrees=False)
    assert calibrate(picks) == Trust(0.8, 0.0, 1.0, 50)


def test_a_band_where_the_model_routed_better_isnt_trusted():
    # The meaning pick agrees 29 times in 30; the model's routing every time.
    picks = [*_picks(29, 0.9), Logged(MeaningPick("t9", 0.9, 0.1), "t1", "t1")]
    assert calibrate(picks) is None
    # Where the model was no better, the same agreement is trusted.
    picks = [*_picks(29, 0.9), Logged(MeaningPick("t9", 0.9, 0.1), "t9", "t1")]
    assert calibrate(picks) is not None


def test_a_narrow_margin_over_the_next_can_be_left_out():
    close_calls = [Logged(MeaningPick("t1", 0.95, 0.01), "t2", "t2") for _ in range(10)]
    trust = calibrate(_picks(MIN_PICKS, 0.9, margin=0.05) + close_calls)
    assert trust is not None and trust.margin == 0.02 and not trust.covers(MeaningPick("t1", 0.95, 0.01))


async def _conversations(service: AssistantService) -> None:
    for thread_id, title in (("bread", "Sourdough starter feeding"), ("tax", "Yearly tax return")):
        at = "2026-09-01T10:00:00+00:00"
        await conversations.save(service.store, "owner", Conversation(thread_id, title, at, at))
    await service.conversation_index.sync("owner")


async def test_a_message_the_model_routes_is_logged_with_where_it_ended_up(dispatch, service):
    await _conversations(service)
    inbox = await service.session("owner", "web")
    dispatch.picks.append(Pick("tax", 0.95, ""))
    events = await collect(service.send(inbox, "my sourdough starter smells sour"))
    [sent] = [e for e in events if isinstance(e, Dispatched)]
    [logged] = await routing_picks.logged(service.store, "owner")
    assert (logged.meaning.place, logged.routed) == ("bread", "tax") and len(dispatch.inputs) == 1
    # Until the client sends it on, it counts where it was routed; then where it is, which /move changes.
    assert logged.final == "tax"
    await collect(service.send_dispatched(Session("owner", "web", "bread"), sent.id))
    [logged] = await routing_picks.logged(service.store, "owner")
    assert logged.final == "bread"


async def test_a_quick_question_counts_where_it_was_answered(dispatch, service):
    await _conversations(service)
    dispatch.picks.append(Pick(QUICK, 0.95, ""))
    await collect(service.send(await service.session("owner", "web"), "what's the tax rate on bread?"))
    [logged] = await routing_picks.logged(service.store, "owner")
    assert logged.final == QUICK and logged.meaning.place in ("bread", "tax")


async def test_where_the_logged_picks_trust_it_the_message_is_routed_without_the_model(dispatch, service):
    await _conversations(service)
    for _ in range(MIN_PICKS):
        await routing_picks.log(service.store, "owner", MeaningPick("bread", 0.05, 0.05), "bread", ["bread", "tax"])
    inbox = await service.session("owner", "web")
    events = await collect(service.send(inbox, "feeding the sourdough starter twice a day?"))
    [sent] = [e for e in events if isinstance(e, Dispatched)]
    assert sent.thread_id == "bread" and dispatch.inputs == []
    assert len(await routing_picks.logged(service.store, "owner")) == MIN_PICKS + 1


async def test_without_the_meaning_index_the_model_routes_and_nothing_is_logged(dispatch, service):
    inbox = await service.session("owner", "web")
    await collect(service.send(inbox, "plan my week"))
    assert len(dispatch.inputs) == 1 and await routing_picks.logged(service.store, "owner") == []
