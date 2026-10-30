"""The token ledger: every model call recorded with its purpose, conversation and channel, its
tokens split among the system prompt, history, the user's message, tools and the reply, and the
report by day, model, conversation, job, skill and tool, with cost where the model has a price."""

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGenerationChunk

import assistant.core.graph as graph_module
from assistant.core.agent import Session
from assistant.core.config import settings
from assistant.core.usage import prices
from assistant.core.usage.tokens import active_skill, input_parts, job_of, output_parts
from tests.conftest import Script, ScriptedModel, collect


def _usage(input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> UsageMetadata:
    return UsageMetadata(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        input_token_details={"cache_read": cache_read, "cache_creation": cache_write},
    )


def test_a_tool_result_is_the_tools_in_the_call_right_after_it_and_history_later():
    messages = [
        SystemMessage("s" * 400),
        HumanMessage("h" * 40),
        AIMessage("", tool_calls=[{"name": "web_fetch", "args": {"url": "x"}, "id": "1"}]),
        ToolMessage("p" * 4000, tool_call_id="1", name="web_fetch"),
    ]
    parts = {(p.kind, p.name): p.input_tokens for p in input_parts(messages, 1110)}
    assert sum(parts.values()) == 1110
    assert parts[("tool", "web_fetch")] > parts[("system", "")] > parts[("history", "")]
    later = [*messages, AIMessage("done"), HumanMessage("thanks")]
    kinds = {(p.kind, p.name) for p in input_parts(later, 1200)}
    assert ("tool", "web_fetch") not in kinds and ("user", "") in kinds


def test_output_goes_to_the_reply_and_to_the_tools_it_calls():
    reply = AIMessage("ok", tool_calls=[{"name": "bash", "args": {"command": "x" * 200}, "id": "1"}])
    parts = {(p.kind, p.name): p.output_tokens for p in output_parts(reply, 60)}
    assert sum(parts.values()) == 60 and parts[("tool", "bash")] > parts[("reply", "")]


def test_the_skill_in_use_and_the_job_a_conversation_belongs_to():
    load = AIMessage("", tool_calls=[{"name": "use_skill", "args": {"name": "news-digest"}, "id": "1"}])
    assert active_skill([HumanMessage("go"), load, ToolMessage("steps", tool_call_id="1")]) == "news-digest"
    assert active_skill([HumanMessage("go"), load, HumanMessage("next")]) is None
    assert job_of("job:morning-news:2026-10-03T09:00") == "morning-news" and job_of("owner:abc") is None


def test_cost_uses_the_cache_prices_and_overrides(monkeypatch):
    # 1M fresh input at $4, 1M cache reads at $0.20, 1M output at $20 (Claude Opus 5.5).
    assert prices.cost("claude-opus-5-5", 2_000_000, 1_000_000, 0, 1_000_000) == pytest.approx(24.2)
    assert prices.cost("qwen3", 1000, 0, 0, 1000) is None
    monkeypatch.setattr(settings, "model_prices", {"qwen3": {"input": 1, "output": 2}})
    assert prices.cost("qwen3", 1_000_000, 0, 0, 1_000_000) == pytest.approx(3.0)


async def test_replies_are_recorded_with_their_conversation_tools_and_skill(service, script):
    script.reply(
        "",
        tool_calls=[{"name": "use_skill", "args": {"name": "nope"}, "id": "c1"}],
        usage_metadata=_usage(900, 30, cache_read=600),
    )
    script.reply("done", usage_metadata=_usage(1000, 20, cache_read=850))
    session = await service.session("owner", "cli")
    await collect(service.send(session, "go"))
    report = await service.token_report(7)
    assert report.total.calls == 2 and report.total.input_tokens == 1900 and report.total.cache_read_tokens == 1450
    assert [(r.name, r.calls) for r in report.by_purpose] == [("reply", 2)]
    assert [r.name for r in report.by_channel] == ["cli"]
    assert report.by_conversation[0].name == session.thread_id
    assert [(r.name, r.calls) for r in report.by_skill] == [("nope", 1)]
    assert [r.name for r in report.by_tool] == ["use_skill"]
    assert report.estimated_calls == 0


async def test_a_call_without_reported_usage_is_estimated(service, script):
    script.reply("hello there")
    await collect(service.send(await service.session("owner", "cli"), "hi"))
    report = await service.token_report(7)
    assert report.estimated_calls == 1 and report.total.input_tokens > 0 and report.total.output_tokens > 0


async def test_titles_are_recorded_as_titles_outside_any_conversation(service, monkeypatch):
    import assistant.core.conversation.titles as titles_module
    from assistant.core.llm.choice import ModelChoice

    script = Script()
    script.reply("Trip to Rome\nTags: rome", usage_metadata=_usage(300, 5))
    monkeypatch.setattr(titles_module, "build_llm", lambda choice, model: script.model())
    titler = titles_module.build_titler(ModelChoice("anthropic", "m", "m"), service._storage.usage)
    assert (await titler("User: plan my trip to Rome")).title == "Trip to Rome"
    report = await service.token_report(7)
    assert [(r.name, r.input_tokens) for r in report.by_purpose] == [("title", 300)]
    assert report.by_conversation == []


class _Streaming(ScriptedModel):
    """Streams each reply word by word, then reports usage in a last chunk, as providers do."""

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        message = next(self.messages)
        text = message if isinstance(message, str) else str(message.content)
        for word in text.split():
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=word + " "))
            if run_manager:
                await run_manager.on_llm_new_token(word + " ", chunk=chunk)
            yield chunk
        yield ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=_usage(10, 2)))


async def test_metered_replies_still_stream_and_record_the_streamed_usage(service, monkeypatch):
    from assistant.core.events import TextDelta

    script = Script()
    script.reply("hello there")
    monkeypatch.setattr(graph_module, "build_llm", lambda choice, model: _Streaming(messages=script._next()))
    service._use_model(service._model)
    events = await collect(service.send(await service.session("owner", "cli"), "hi"))
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["hello ", "there "]
    report = await service.token_report(7)
    assert (report.total.input_tokens, report.total.output_tokens, report.estimated_calls) == (10, 2, 0)


async def test_a_conversations_stats_count_only_its_own_messages_tokens_and_tool_calls(service, script):
    script.reply(
        "",
        tool_calls=[{"name": "use_skill", "args": {"name": "nope"}, "id": "c1"}],
        usage_metadata=_usage(900, 30, cache_read=600),
    )
    script.reply("done", usage_metadata=_usage(1000, 20, cache_read=850))
    session = Session("owner", "cli", await service.new_thread("owner"))
    await collect(service.send(session, "go"))
    script.reply("elsewhere", usage_metadata=_usage(5000, 500))
    await collect(service.send(Session("owner", "web", await service.new_thread("owner")), "other"))

    stats = await service.conversation_stats("owner", session.thread_id)
    assert (stats.messages, stats.model_calls, stats.tool_calls) == (2, 2, 1)
    assert (stats.input_tokens, stats.cache_read_tokens, stats.output_tokens) == (1900, 1450, 50)
    assert stats.started_at


async def test_a_new_conversation_has_no_stats(service):
    stats = await service.conversation_stats("owner", await service.new_thread("owner"))
    assert (stats.messages, stats.model_calls, stats.tool_calls, stats.input_tokens) == (0, 0, 0, 0)
    assert stats.started_at is None
