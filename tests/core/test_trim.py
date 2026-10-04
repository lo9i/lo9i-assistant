"""Old tool results: once the prompt cache has expired, results before the last TRIM_KEEP_TURNS user
turns are sent as stubs from then on; the checkpoint keeps them whole."""

from datetime import UTC, datetime, timedelta
from typing import cast

from langchain_core.messages import HumanMessage, ToolMessage

from assistant.core.config import settings
from assistant.core.conversation.trim import trimmed
from tests.conftest import collect

_LONG = "python3 -c \"print('x' * 3000)\""


async def _state(service, session):
    return (await service._graph.aget_state({"configurable": {"thread_id": session.thread_id}})).values


async def _idle(service, session, minutes: float) -> None:
    config = {"configurable": {"thread_id": session.thread_id}}
    last = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
    await service._graph.aupdate_state(config, {"last_model_call": last}, as_node="agent")


def _results(request) -> list[str]:
    return [m.text for m in request if isinstance(m, ToolMessage)]


async def _read_then_chat(service, script, session) -> None:
    script.call("bash", command=_LONG).reply("read it")
    await collect(service.send(session, "read the page"))
    await collect(service.send(session, "thanks"))


async def test_results_stay_whole_while_the_cache_is_warm(service, script):
    session = await service.session("u", "cli")
    await _read_then_chat(service, script, session)
    await collect(service.send(session, "and now"))
    assert "x" * 3000 in _results(script.requests[-1])[0]
    assert "trimmed_before" not in await _state(service, session)


async def test_after_the_cache_expires_old_results_are_stubs_from_then_on(service, script):
    session = await service.session("u", "cli")
    await _read_then_chat(service, script, session)
    await _idle(service, session, settings.prompt_cache_minutes + 1)
    await collect(service.send(session, "back again"))
    await collect(service.send(session, "one more"))
    for request in script.requests[-2:]:
        [result] = _results(request)
        assert result.startswith("[Left out to save space") and "Call bash again" in result
    state = await _state(service, session)
    assert state["usage_anchor"] is None or state["usage_anchor"]["messages"] == len(state["messages"])
    stored = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert "x" * 3000 in stored[0].text


async def test_results_in_the_last_turns_are_kept(service, script):
    session = await service.session("u", "cli")
    script.call("bash", command=_LONG).reply("read it")
    await collect(service.send(session, "read the page"))
    await _idle(service, session, settings.prompt_cache_minutes + 1)
    await collect(service.send(session, "what did it say"))
    assert "x" * 3000 in _results(script.requests[-1])[0]


async def test_short_results_are_never_trimmed(service, script):
    session = await service.session("u", "cli")
    script.call("bash", command="echo hi").reply("done")
    await collect(service.send(session, "say hi"))
    await collect(service.send(session, "thanks"))
    await _idle(service, session, settings.prompt_cache_minutes + 1)
    await collect(service.send(session, "back"))
    assert "hi" in _results(script.requests[-1])[0]
    assert "trimmed_before" not in await _state(service, session)


def test_a_result_with_files_is_stubbed_without_them():
    image = {"type": "non_standard", "value": {"upload": {"path": "a.png", "name": "a.png", "media_type": "image/png"}}}
    messages = [
        HumanMessage("show it"),
        ToolMessage("one image", tool_call_id="c1", name="mcp__cam__snap", artifact=[image]),
        HumanMessage("thanks"),
    ]
    sent = trimmed(messages, 0, 2)
    assert sent[1].text.startswith("[Left out") and not cast(ToolMessage, sent[1]).artifact
    assert trimmed(messages, 0, 1) == messages
