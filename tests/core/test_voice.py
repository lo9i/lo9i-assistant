"""Live voice calls from the service's side (core/voice/, core/agent/voice_calls.py): the OpenAI key, what's said kept
in the conversation and left out of model calls, the voice's requests run as the conversation's messages, tool calls
answered once per call id, and OpenAI's API as the daemon speaks it. No key is real: OpenAI is faked."""

import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from assistant.core.agent import Session, VoiceCallError, VoiceKeyError
from assistant.core.config import settings
from assistant.core.llm.choice import ModelChoice
from assistant.core.voice import key as voice_key
from assistant.core.voice.heard import Heard, Line
from assistant.core.voice.realtime import MODEL, OpenAIRealtime, RealtimeError
from assistant.core.voice.spoken import VOICE_CHANNEL, message, without_spoken
from assistant.core.voice.tool_calls import KEPT, ToolCalls
from tests.conftest import collect
from tests.core.fake_realtime import GOOD_KEY, FakeRealtime

THREAD = "owner:call"
SESSION = Session("owner", VOICE_CHANNEL, THREAD)


@pytest.fixture
def realtime(service) -> FakeRealtime:
    fake = FakeRealtime()
    service.realtime = fake
    return fake


async def test_the_key_is_the_saved_one_else_the_openai_models_else_envs(service, realtime, monkeypatch):
    assert (await service.voice_call_settings()).key_source == ""
    monkeypatch.setattr(settings, "openai_api_key", "sk-env")
    assert (await service.voice_call_key()) == "sk-env"
    # A key for another OpenAI-compatible server isn't OpenAI's.
    monkeypatch.setattr(settings, "openai_base_url", "http://localhost:11434/v1")
    assert (await service.voice_call_settings()).key_source == ""
    found = await voice_key.current(
        service.store, service.secrets, ModelChoice("openai", "m", "w", {"api_key": "sk-m"})
    )
    assert (found.value, found.source) == ("sk-m", "model")
    with pytest.raises(VoiceKeyError, match="Incorrect API key"):
        await service.set_voice_call_key("sk-bad")
    status = await service.set_voice_call_key(f" {GOOD_KEY} ")
    assert (status.key_source, status.model) == ("saved", MODEL)
    assert await service.voice_call_key() == GOOD_KEY
    assert (await service.remove_voice_call_key()).key_source == ""


async def test_what_is_said_is_kept_shown_and_left_out_of_model_calls(service, script):
    lines = [Line("user", "what's on tomorrow?"), Line("voice", "Let me check.")]
    assert await service.keep_said_in_call(SESSION, lines)
    shown = await service.conversation_messages(THREAD)
    assert [(m.role, m.text, m.voice) for m in shown] == [
        ("user", "what's on tomorrow?", "said"),
        ("assistant", "Let me check.", "said"),
    ]
    # The conversation is listed, as one written in.
    assert (await service.conversation("owner", THREAD)).thread_id == THREAD
    script.reply("Two meetings.")
    await collect(service.ask_from_voice_call(SESSION, "List tomorrow's meetings", lines))
    sent = script.requests[-1]
    assert not any(m.text == "Let me check." for m in sent)
    # The request says it comes from a call, with what was said since the last answer.
    request = sent[-1]
    assert isinstance(request, HumanMessage) and "live voice call" in request.text
    assert "User: what's on tomorrow?\nVoice: Let me check." in request.text
    shown = await service.conversation_messages(THREAD)
    assert [(m.role, m.text, m.voice) for m in shown[-2:]] == [
        ("user", "List tomorrow's meetings", "asked"),
        ("assistant", "Two meetings.", ""),
    ]
    # The voice speaking after the reply doesn't make its words the assistant's last reply.
    assert await service.keep_said_in_call(SESSION, [Line("voice", "You have two meetings.")])
    assert await service.last_reply(THREAD) == "Two meetings."


async def test_nothing_is_kept_while_the_conversation_waits_for_an_answer(service, script):
    script.call("bash", command="rm -rf /tmp/x")
    events = await collect(service.ask_from_voice_call(SESSION, "clean up", []))
    assert any(type(e).__name__ == "ApprovalRequired" for e in events)
    assert not await service.keep_said_in_call(SESSION, [Line("user", "go ahead")])
    assert not any(m.voice == "said" for m in await service.conversation_messages(THREAD))


async def test_what_was_said_after_the_last_request_goes_with_the_next_message(service, script):
    await service.voice_call_ended(SESSION, [Line("user", "and book the room"), Line("voice", "Sure.")])
    await collect(service.send(Session("owner", "web", THREAD), "did you book it?"))
    note = script.requests[-1][-1].text
    assert "went on after your last answer" in note and "User: and book the room\nVoice: Sure." in note
    await collect(service.send(Session("owner", "web", THREAD), "thanks"))
    assert "book the room" not in script.requests[-1][-1].text


async def test_a_call_cant_be_in_the_inbox(service, realtime):
    inbox = await service.inbox_thread("owner")
    with pytest.raises(VoiceCallError):
        await service.voice_call_session("owner", inbox)
    settings_sent = await service.voice_call_session("owner", THREAD)
    assert settings_sent["model"] == MODEL and settings_sent["tools"][0]["name"] == "ask_assistant"


def test_lines_come_out_in_the_calls_order_once_their_words_are_known():
    heard = Heard()
    heard.added({"id": "u1", "type": "message", "role": "user"})
    heard.added({"id": "v1", "type": "message", "role": "assistant"})
    heard.added({"id": "f1", "type": "function_call"})
    # The voice answered before the transcription of what the user said completed.
    heard.heard("v1", "voice", "Hello!")
    assert heard.ready() == []
    heard.heard("u1", "user", " hi there ")
    assert heard.ready() == [Line("user", "hi there"), Line("voice", "Hello!")]
    heard.added({"id": "u2", "type": "message", "role": "user"})
    heard.heard("v9", "voice", "never added")
    assert heard.ready() == []
    # At the end, what's known goes out; what was never heard is left out.
    assert heard.rest() == [Line("voice", "never added")]


async def test_a_tool_call_is_answered_once_per_call_id(service):
    calls = ToolCalls(service.store)
    asked: list[str] = []
    gate = asyncio.Event()

    async def ask() -> str:
        asked.append("asked")
        await gate.wait()
        return f"answer {len(asked)}"

    first = asyncio.create_task(calls.answer("call_1", ask))
    second = asyncio.create_task(calls.answer("call_1", ask))
    await asyncio.sleep(0)
    gate.set()
    assert await first == await second == "answer 1"
    # Made again later, even after a restart (the log is in the Store), it gets the first result.
    assert await ToolCalls(service.store).answer("call_1", ask) == "answer 1"
    assert asked == ["asked"]


async def test_a_failed_tool_call_is_asked_again_and_the_log_keeps_the_latest(service):
    calls = ToolCalls(service.store)

    async def fail() -> str:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await calls.answer("call_x", fail)

    async def ok() -> str:
        return "fine"

    assert await calls.answer("call_x", ok) == "fine"
    for n in range(KEPT + 2):
        await calls.answer(f"call_{n}", ok)
    assert len(await service.store.asearch(("voice_tool_calls",), limit=1000)) == KEPT


async def test_a_call_is_made_with_the_offer_and_its_settings_and_its_id_read_from_location():
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/hangup"):
            return httpx.Response(404)
        headers = {"Location": "/v1/realtime/calls/rtc_abc"}
        return httpx.Response(201, text="v=0 answer", headers=headers)

    realtime = OpenAIRealtime(httpx.MockTransport(answer))
    found = await realtime.call("sk-1", "v=0 offer", {"type": "realtime", "model": MODEL})
    assert (found.call_id, found.sdp) == ("rtc_abc", "v=0 answer")
    request = seen[0]
    assert (request.method, str(request.url)) == ("POST", "https://api.openai.com/v1/realtime/calls")
    assert request.headers["authorization"] == "Bearer sk-1"
    body = request.read().decode()
    assert "multipart/form-data" in request.headers["content-type"]
    assert 'name="sdp"' in body and "v=0 offer" in body
    assert 'name="session"' in body and json.dumps({"type": "realtime", "model": MODEL}) in body
    # A call that ended already is hung up all the same.
    await realtime.hang_up("sk-1", "rtc_abc")
    assert seen[-1].url.path == "/v1/realtime/calls/rtc_abc/hangup"


async def test_openais_refusal_says_why():
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided: sk-bad"}})

    realtime = OpenAIRealtime(httpx.MockTransport(refuse))
    with pytest.raises(RealtimeError, match="Incorrect API key provided"):
        await realtime.check_key("sk-bad")
    with pytest.raises(RealtimeError, match="Incorrect API key"):
        await realtime.call("sk-bad", "offer", {})


def test_spoken_messages_are_left_out_by_their_mark():
    said = [message(Line("user", "hi"), datetime.now(UTC)), message(Line("voice", "hello"), datetime.now(UTC))]
    kept = [HumanMessage("typed"), *said, AIMessage("reply")]
    assert [m.text for m in without_spoken(kept)] == ["typed", "reply"]
