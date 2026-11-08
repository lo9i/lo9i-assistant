"""Saved facts: only basic ones are in every system prompt, within a budget of tokens; the others, and the summaries of
past conversations, come into a turn when the user's message is close to them in meaning, once per conversation, and
stay in its later epochs' prompts."""

import logging

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from lo9i.core.agent import Session
from lo9i.core.config import settings
from lo9i.core.conversation import relevant
from lo9i.core.conversation.prompt import build_system_prompt
from lo9i.core.events import Dispatched
from lo9i.core.memory import episodes, facts
from lo9i.core.memory.episodes import Episode
from lo9i.core.usage.tokens import estimate_text
from tests.conftest import collect

_GAS = "gas service is with Naturgy, meter 14246967"


@pytest.fixture(autouse=True)
def close_by_shared_words(monkeypatch):
    """The fake embedder's vectors are bags of words: sharing two of a handful is close."""
    monkeypatch.setattr(settings, "memory_relevant_similarity", 0.3)
    monkeypatch.setattr(settings, "memory_relevant_conversations_similarity", 0.3)
    monkeypatch.setattr(settings, "memory_relevant_conversations_margin", 0.0)


async def _conversation(service) -> Session:
    return Session("u", "web", await service.new_thread("u"))


async def _saved(service, text: str, basic: bool = False) -> str:
    fact_id = await facts.add(service.store, "u", text, basic)
    await service.memory_index.sync_all()
    return fact_id


async def _summary(service, summary: str, ended_at: str = "2026-10-21T16:00:00") -> str:
    await episodes.save(service.store, "u", Episode("2026-10-21T15:00:00", ended_at, summary))
    await service.memory_index.sync_all()
    return next(e.id for e in await episodes.load_all(service.store, "u") if e.summary == summary)


def _last_message(script) -> str:
    message = [m for m in script.requests[-1] if isinstance(m, HumanMessage)][-1]
    return "\n".join(b.get("text", "") for b in message.content if isinstance(b, dict))


async def test_only_basic_facts_are_in_the_system_prompt(service, script):
    await _saved(service, "the lo9i repo is at ~/projects/lo9i", basic=True)
    await _saved(service, _GAS)
    await collect(service.send(await _conversation(service), "hi"))
    system = str(script.requests[-1][0].content)
    assert "the lo9i repo is at ~/projects/lo9i" in system and "Naturgy" not in system


async def test_basic_facts_past_the_budget_are_left_out_newest_first_and_logged(service, monkeypatch, caplog):
    oldest = await facts.add(service.store, "u", "the oldest basic fact of all", basic=True)
    for text in ["a middle basic fact", "the newest basic fact"]:
        await facts.add(service.store, "u", text, basic=True)
    saved = await facts.load_all(service.store, "u")
    two = sum(estimate_text(facts.line(f) + "\n") for f in saved if f.id != oldest)
    monkeypatch.setattr(settings, "memory_basic_facts_tokens", two)
    with caplog.at_level(logging.WARNING):
        prompt = await build_system_prompt(service.store, "u", "lo9i", "")
    assert "the newest basic fact" in prompt and "a middle basic fact" in prompt and "oldest" not in prompt
    assert any(oldest in r.getMessage() and "budget" in r.getMessage() for r in caplog.records)


async def test_a_message_brings_up_the_facts_it_touches_once_per_conversation(service, script):
    gas = await _saved(service, _GAS)
    await _saved(service, "likes jazz records")
    session = await _conversation(service)
    await collect(service.send(session, "check my gas service bill"))
    said = _last_message(script)
    assert "# Relevant facts" in said and f"[{gas}] {_GAS}" in said and "jazz" not in said
    assert "# Relevant facts" not in str(script.requests[-1][0].content)  # the message shows it, once
    await collect(service.send(session, "and the gas service next month?"))
    assert "# Relevant facts" not in _last_message(script)
    other = await _conversation(service)
    await collect(service.send(other, "the gas service again"))
    assert f"[{gas}]" in _last_message(script)


async def test_basic_facts_never_come_as_relevant(service, script):
    await _saved(service, _GAS, basic=True)
    await collect(service.send(await _conversation(service), "check my gas service bill"))
    assert "# Relevant facts" not in _last_message(script)


async def test_facts_brought_up_stay_in_the_prompt_of_later_epochs(service, script, digests, monkeypatch):
    monkeypatch.setattr(settings, "epoch_max_tokens", 1)
    monkeypatch.setattr(settings, "epoch_keep_turns", 1)
    gas = await _saved(service, _GAS)
    session = await _conversation(service)
    await collect(service.send(session, "check my gas service bill"))
    await collect(service.send(session, "thanks, something else now"))
    system = str(script.requests[-1][0].content)
    assert "# Relevant facts" in system and f"[{gas}] {_GAS}" in system
    assert "# Relevant facts" not in _last_message(script)


async def test_the_inbox_brings_them_up_each_time_and_keeps_none(service, script):
    gas = await _saved(service, _GAS)
    session = await service.session("u", "web")
    for text in ["check my gas service bill", "the gas service, again?"]:
        await collect(service.send(session, text))
        assert f"[{gas}]" in _last_message(script)
    assert await relevant.kept(service.store, "u", session.thread_id) == relevant.Brought()


@pytest.mark.usefixtures("dispatch")
async def test_a_message_sent_on_carries_its_facts_and_its_conversation_keeps_them(service, script):
    gas = await _saved(service, _GAS)
    events = await collect(service.send(await service.session("u", "web"), "check my gas service bill"))
    moved = next(e for e in events if isinstance(e, Dispatched))
    new = await _conversation(service)
    await collect(service.send_dispatched(new, moved.id))
    assert _last_message(script).count("# Relevant facts") == 1
    assert [f.id for f in (await relevant.kept(service.store, "u", new.thread_id)).facts] == [gas]
    await service.delete_conversation("u", new.thread_id)
    assert await relevant.kept(service.store, "u", new.thread_id) == relevant.Brought()


async def test_without_the_embedding_model_messages_go_on_without_them(service, script, embedder):
    await _saved(service, _GAS)
    embedder.failing = True
    await collect(service.send(await _conversation(service), "check my gas service bill"))
    assert script.requests and "# Relevant facts" not in _last_message(script)


async def test_remember_saves_a_basic_fact_only_as_one_short_line(service, script):
    script.call("remember", fact="the lo9i repo is at ~/projects/lo9i", basic=True)
    script.call("remember", fact="x" * (facts.BASIC_MAX_CHARS + 1), basic=True).reply("ok")
    await collect(service.send(await _conversation(service), "remember"))
    [saved] = await facts.load_all(service.store, "u")
    assert saved.basic and saved.text == "the lo9i repo is at ~/projects/lo9i"
    refused = [m for m in script.requests[-1] if isinstance(m, ToolMessage)][-1]
    assert "Not saved: a basic fact is one short line" in str(refused.content)


async def test_marking_basic_keeps_the_id_and_editing_keeps_it_basic(service):
    fact_id = await facts.add(service.store, "u", "the lo9i repo is at ~/projects/lo9i")
    marked = await service.set_fact_basic("u", fact_id, True)
    assert (marked.id, marked.basic) == (fact_id, True)
    edited = await service.edit_fact("u", fact_id, "the lo9i repo is at ~/code/lo9i")
    assert edited.basic and edited.id != fact_id


_INVOICE = "The user pasted a Naturgy gas service invoice and it was added to expenses."


async def test_no_past_conversation_is_in_the_system_prompt(service):
    await _summary(service, _INVOICE)
    prompt = await build_system_prompt(service.store, "u", "lo9i", "")
    assert "Naturgy" not in prompt and "conversations" not in prompt.lower().split("# skills")[-1]


async def test_a_message_brings_up_the_past_conversations_it_touches_once_and_they_stay(
    service, script, digests, monkeypatch
):
    invoice = await _summary(service, _INVOICE)
    await _summary(service, "Planned holidays: Rome, Florence.", ended_at="2026-10-22T16:00:00")
    session = await _conversation(service)
    await collect(service.send(session, "add the gas service invoice to expenses"))
    said = _last_message(script)
    assert "# Relevant conversations" in said and _INVOICE in said and "Rome" not in said
    await collect(service.send(session, "and the gas service invoice from last month?"))
    assert "# Relevant conversations" not in _last_message(script)
    monkeypatch.setattr(settings, "epoch_max_tokens", 1)
    monkeypatch.setattr(settings, "epoch_keep_turns", 1)
    await collect(service.send(session, "thanks, something else now"))
    system = str(script.requests[-1][0].content)
    assert "# Relevant conversations" in system and _INVOICE in system
    assert [e.id for e in (await relevant.kept(service.store, "u", session.thread_id)).episodes] == [invoice]


async def test_a_past_conversation_has_to_stand_out_from_the_rest(service, script, monkeypatch):
    monkeypatch.setattr(settings, "memory_relevant_conversations_margin", 0.2)
    for place in ["Rome", "Paris", "Lisbon"]:
        await _summary(service, f"Planned a trip to {place}.")
    await collect(service.send(await _conversation(service), "plan a trip"))
    assert "# Relevant conversations" not in _last_message(script)
    await collect(service.send(await _conversation(service), "the trip to Lisbon"))
    said = _last_message(script)
    assert "Lisbon" in said.split("# Relevant conversations")[-1] and "Rome" not in said


async def test_at_most_a_few_past_conversations_a_message(service, script):
    for n in range(5):
        await _summary(service, f"Talked about the gas service invoice number {n}.")
    await collect(service.send(await _conversation(service), "the gas service invoice"))
    note = _last_message(script).split("# Relevant conversations")[-1]
    assert note.count("Talked about the gas service invoice") == settings.memory_relevant_conversations == 3


@pytest.mark.usefixtures("dispatch")
async def test_a_message_sent_on_carries_its_past_conversations(service, script):
    invoice = await _summary(service, _INVOICE)
    events = await collect(service.send(await service.session("u", "web"), "add the gas service invoice"))
    moved = next(e for e in events if isinstance(e, Dispatched))
    new = await _conversation(service)
    await collect(service.send_dispatched(new, moved.id))
    assert _last_message(script).count("# Relevant conversations") == 1
    assert [e.id for e in (await relevant.kept(service.store, "u", new.thread_id)).episodes] == [invoice]
