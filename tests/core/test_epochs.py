"""Epochs: new ones start on a size limit or an idle gap, rebuild the prompt with a summary, and
leave memory to the memory writer."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import AIMessage

from assistant.core.config import settings
from assistant.core.conversation import pending, summaries
from assistant.core.conversation.digest import MemoryDigest
from assistant.core.conversation.epochs import cut_index, estimate_tokens, usage_anchor
from tests.conftest import collect


def _reply_with_usage(tokens_in: int) -> dict:
    return {"usage_metadata": {"input_tokens": tokens_in, "output_tokens": 10, "total_tokens": tokens_in + 10}}


async def _state(service, session):
    return (await service._graph.aget_state({"configurable": {"thread_id": session.thread_id}})).values


async def test_system_prompt_stays_identical_within_an_epoch(service, script):
    session = await service.session("u", "cli")
    for text in ["one", "two", "three"]:
        await collect(service.send(session, text))
    assert len({r[0].content for r in script.requests}) == 1


async def test_size_limit_starts_a_new_epoch_from_reported_tokens(service, script, summaries, monkeypatch):
    monkeypatch.setattr(settings, "epoch_max_tokens", 5000)
    monkeypatch.setattr(settings, "epoch_keep_turns", 1)
    script.reply("a", **_reply_with_usage(1000)).reply("b", **_reply_with_usage(6000)).reply(
        "c", **_reply_with_usage(800)
    )
    session = await service.session("u", "cli")
    await collect(service.send(session, "one"))
    await collect(service.send(session, "two"))
    assert summaries.inputs == []
    await collect(service.send(session, "three"))
    state = await _state(service, session)
    assert len(summaries.inputs) == 1 and state["epoch_start"] == 4
    assert state["usage_anchor"] == {"tokens": 810, "messages": 6}
    assert len(script.requests[-1]) == 2  # system prompt + the new message only


@pytest.fixture
def small_epochs(monkeypatch):
    monkeypatch.setattr(settings, "epoch_max_tokens", 1)
    monkeypatch.setattr(settings, "epoch_keep_turns", 1)


async def test_a_new_epoch_waits_only_for_the_summary(service, script, digests, small_epochs):
    session = await service.session("u", "cli")
    await collect(service.send(session, "one"))
    await collect(service.send(session, "two"))
    assert "summary 1" in (await _state(service, session))["system_prompt"]
    assert digests.inputs == [] and len(await pending.load_all(service.store, "u")) == 1


async def test_the_memory_writer_digests_the_archived_part(service, script, digests, small_epochs):
    digests.result = lambda data: MemoryDigest(
        episode_summary="talked about agents",
        profile=data.profile.model_copy(update={"work": ["software engineer"]}),
        new_facts=["dentist on Friday"],
        outdated_fact_ids=[],
    )
    session = await service.session("u", "cli")
    await collect(service.send(session, "first-message"))
    await collect(service.send(session, "second-message"))
    await service.memory_writer.write_all()
    assert len(digests.inputs) == 1 and "first-message" in digests.inputs[0].transcript
    assert "second-message" not in digests.inputs[0].transcript
    memory = await service.memory_snapshot("u")
    assert memory.profile["work"] == ["software engineer"] and memory.facts == ["dentist on Friday"]
    assert memory.episodes == ["talked about agents"] and await pending.load_all(service.store, "u") == []


async def test_a_failed_digest_is_tried_again(service, script, digests, small_epochs):
    session = await service.session("u", "cli")
    await collect(service.send(session, "one"))
    await collect(service.send(session, "two"))
    digests.result = lambda data: (_ for _ in ()).throw(RuntimeError("model down"))
    await service.memory_writer.write_all()
    assert len(await pending.load_all(service.store, "u")) == 1
    digests.result = lambda data: MemoryDigest(
        episode_summary="later", profile=data.profile, new_facts=[], outdated_fact_ids=[]
    )
    await service.memory_writer.write_all()
    assert (await service.memory_snapshot("u")).episodes == ["later"]


async def test_a_deleted_conversation_leaves_nothing_to_digest(service, script, digests, small_epochs):
    session = await service.session("u", "cli")
    await collect(service.send(session, "one"))
    await collect(service.send(session, "two"))
    await service.delete_conversation("u", session.thread_id)
    await service.memory_writer.write_all()
    assert digests.inputs == [] and await pending.load_all(service.store, "u") == []


async def test_idle_gap_starts_a_new_epoch_keeping_only_the_new_message(service, script, summaries):
    session = await service.session("u", "cli")
    await collect(service.send(session, "before the break"))
    config = {"configurable": {"thread_id": session.thread_id}}
    old = (datetime.now(UTC) - timedelta(hours=settings.epoch_idle_hours + 1)).isoformat()
    await service._graph.aupdate_state(config, {"last_activity": old}, as_node="epoch")
    await collect(service.send(session, "back"))
    state = await _state(service, session)
    assert len(summaries.inputs) == 1 and len(state["messages"]) - state["epoch_start"] == 2


def test_cut_index_keeps_whole_turns():
    from langchain_core.messages import HumanMessage, ToolMessage

    messages = [
        HumanMessage("1"),
        AIMessage("", tool_calls=[{"name": "bash", "args": {}, "id": "t"}]),
        ToolMessage("out", tool_call_id="t"),
        AIMessage("a"),
        HumanMessage("2"),
        AIMessage("b"),
    ]
    assert cut_index(messages, 0, 1) == 4
    assert cut_index(messages, 0, 5) == 0


def test_estimate_prefers_reported_tokens():
    state = {"messages": ["x"] * 3, "usage_anchor": {"tokens": 1000, "messages": 3}, "system_prompt": ""}
    assert estimate_tokens(state) == 1000
    assert usage_anchor(AIMessage("x"), 3) is None


async def test_stopping_cuts_a_digest_short_and_its_part_stays(service, script, digests, small_epochs):
    digests.answer = asyncio.Event()
    session = await service.session("u", "cli")
    await collect(service.send(session, "one"))
    await collect(service.send(session, "two"))
    stop = asyncio.Event()
    writer = asyncio.create_task(service.memory_writer.run(stop))
    async with asyncio.timeout(5):
        while not digests.inputs:
            await asyncio.sleep(0.01)
    stop.set()
    async with asyncio.timeout(5):
        await writer
    assert len(await pending.load_all(service.store, "u")) == 1


async def test_the_running_writer_digests_a_new_part_on_its_own(service, script, digests, small_epochs):
    stop = asyncio.Event()
    writer = asyncio.create_task(service.memory_writer.run(stop))
    session = await service.session("u", "cli")
    await collect(service.send(session, "one"))
    await collect(service.send(session, "two"))
    async with asyncio.timeout(5):
        while await pending.load_all(service.store, "u"):
            await asyncio.sleep(0.01)
    stop.set()
    await writer
    assert len(digests.inputs) == 1


async def test_a_new_epochs_summary_is_kept_for_routing_and_goes_with_the_conversation(
    service, script, digests, small_epochs
):
    session = await service.session("u", "cli")
    await collect(service.send(session, "one"))
    await collect(service.send(session, "two"))
    assert (await summaries.of_user(service.store, "u"))[session.thread_id] == "summary 1"
    await service.delete_conversation("u", session.thread_id)
    assert session.thread_id not in await summaries.of_user(service.store, "u")


async def test_conversations_summarized_before_summaries_were_kept_get_theirs_once(
    service, script, digests, small_epochs
):
    session = await service.session("u", "cli")
    await collect(service.send(session, "one"))
    await collect(service.send(session, "two"))
    await service.store.adelete(("conversation_summaries", "u"), session.thread_id)
    assert await service.fill_summaries("u") == 1
    assert (await summaries.of_user(service.store, "u"))[session.thread_id] == "summary 1"
    assert await service.fill_summaries("u") == 0
