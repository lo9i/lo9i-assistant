"""Epochs: new ones start on a size limit or an idle gap, digest memory, and rebuild the prompt."""

from datetime import UTC, datetime, timedelta

from langchain_core.messages import AIMessage

from assistant.core.config import settings
from assistant.core.conversation.digest import EpochDigest
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


async def test_size_limit_starts_a_new_epoch_from_reported_tokens(service, script, digests, monkeypatch):
    monkeypatch.setattr(settings, "epoch_max_tokens", 5000)
    monkeypatch.setattr(settings, "epoch_keep_turns", 1)
    script.reply("a", **_reply_with_usage(1000)).reply("b", **_reply_with_usage(6000)).reply(
        "c", **_reply_with_usage(800)
    )
    session = await service.session("u", "cli")
    await collect(service.send(session, "one"))
    await collect(service.send(session, "two"))
    assert digests.inputs == []
    await collect(service.send(session, "three"))
    state = await _state(service, session)
    assert len(digests.inputs) == 1 and state["epoch_start"] == 4
    assert state["usage_anchor"] == {"tokens": 810, "messages": 6}
    assert len(script.requests[-1]) == 2  # system prompt + the new message only


async def test_new_epoch_rebuilds_prompt_with_memory_and_summary(service, script, digests, monkeypatch):
    monkeypatch.setattr(settings, "epoch_max_tokens", 1)
    monkeypatch.setattr(settings, "epoch_keep_turns", 1)
    digests.result = lambda data: EpochDigest(
        episode_summary="talked about agents",
        conversation_summary="running summary",
        profile=data.profile.model_copy(update={"work": ["software engineer"]}),
        new_facts=["dentist on Friday"],
        outdated_fact_ids=[],
    )
    session = await service.session("u", "cli")
    await collect(service.send(session, "one"))
    await collect(service.send(session, "two"))
    prompt = (await _state(service, session))["system_prompt"]
    for expected in ["Work: software engineer", "dentist on Friday", "talked about agents", "running summary"]:
        assert expected in prompt


async def test_idle_gap_starts_a_new_epoch_keeping_only_the_new_message(service, script, digests):
    session = await service.session("u", "cli")
    await collect(service.send(session, "before the break"))
    config = {"configurable": {"thread_id": session.thread_id}}
    old = (datetime.now(UTC) - timedelta(hours=settings.epoch_idle_hours + 1)).isoformat()
    await service._graph.aupdate_state(config, {"last_activity": old}, as_node="epoch")
    await collect(service.send(session, "back"))
    state = await _state(service, session)
    assert len(digests.inputs) == 1 and len(state["messages"]) - state["epoch_start"] == 2


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
