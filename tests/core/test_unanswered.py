"""A tool that raises ends the run after the model's tool calls were saved but before their results: each call
without a result is sent with a stub, so the conversation goes on, and the failure is logged."""

import logging
import sqlite3

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from assistant.core.conversation.unanswered import answered
from assistant.core.events import Error
from assistant.core.memory import profile
from tests.conftest import collect


def _calls(*ids: str) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": "bash", "args": {}, "id": i} for i in ids])


def test_a_call_without_a_result_gets_a_stub_after_the_results_it_has():
    sent = answered([_calls("a", "b"), ToolMessage("done", tool_call_id="a"), HumanMessage("and now?")])
    assert [type(m).__name__ for m in sent] == ["AIMessage", "ToolMessage", "ToolMessage", "HumanMessage"]
    stub = sent[2]
    assert isinstance(stub, ToolMessage) and stub.tool_call_id == "b" and stub.status == "error"


def test_calls_with_their_results_are_sent_as_they_are():
    messages = [_calls("a"), ToolMessage("done", tool_call_id="a"), AIMessage("ok")]
    assert answered(messages) == messages


async def test_a_conversation_goes_on_after_a_tool_raised(
    service, script, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    async def _locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(profile, "save", _locked)
    script.call("update_profile", section="goals", items=["run a marathon"]).reply("noted")
    session = await service.session("owner", "cli")
    with caplog.at_level(logging.ERROR):
        events = await collect(service.send(session, "remember my goal"))
    assert isinstance(events[-1], Error) and "database is locked" in caplog.text
    await collect(service.send(session, "did it save?"))
    request = script.requests[-1]
    call = next(i for i, m in enumerate(request) if isinstance(m, AIMessage) and m.tool_calls)
    assert isinstance(request[call + 1], ToolMessage) and "didn't finish" in request[call + 1].text
