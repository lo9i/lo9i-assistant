"""Live voice calls through the daemon (daemon/voice_calls.py): the offer and answer, the sideband's events kept in
the conversation, the voice model's tool calls run through the assistant and answered once per call id, and hanging
up. OpenAI is faked (tests/core/fake_realtime.py): no key is real here."""

import asyncio

import httpx
import pytest

from assistant.client.daemon_client import DaemonClient
from assistant.core.agent import Session, VoiceCallError, VoiceChoiceError, VoiceKeyError
from assistant.core.voice.realtime import RealtimeError, SidebandLostError
from assistant.daemon import voice_calls
from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.runs import RunHub
from assistant.daemon.voice_calls import VoiceCalls
from assistant.protocol import CLIENT_HEADER, CLIENT_ID_HEADER
from tests.conftest import collect
from tests.core.fake_realtime import GOOD_KEY, FakeRealtime, asked, user_said, voice_said

THREAD = "owner:call"


@pytest.fixture
async def realtime(service) -> FakeRealtime:
    fake = FakeRealtime()
    service.realtime = fake
    await service.set_voice_call_key(GOOD_KEY)
    return fake


@pytest.fixture
def calls(service) -> VoiceCalls:
    return VoiceCalls(service, RunHub(service.bus))


@pytest.fixture
async def client(service, calls):
    app = create_app(service, RunHub(service.bus), voice_calls=calls)
    transport = httpx.ASGITransport(app=trusted(app))
    headers = {CLIENT_HEADER: "test", CLIENT_ID_HEADER: "me"}
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1", headers=headers) as http:
        yield DaemonClient(http)


async def _ended(service, after: int, thread_id: str) -> None:
    async with asyncio.timeout(10):
        async for event in service.bus.subscribe(after):
            if event.kind == "voice_call" and event.data["thread_id"] == thread_id and not event.data["live"]:
                return


async def test_the_offer_goes_to_openai_with_the_calls_settings_and_its_answer_comes_back(client, realtime):
    answer = await client.voice_calls.start(THREAD, "v=0 the browser's offer")
    assert (answer.call_id, answer.sdp) == ("rtc_1", "answer to v=0 the browser's offer")
    key, offer, session = realtime.calls[0]
    assert (key, offer) == (GOOD_KEY, "v=0 the browser's offer")
    assert session["type"] == "realtime" and [t["name"] for t in session["tools"]] == ["ask_assistant"]
    assert "ask_assistant" in session["instructions"]
    # The daemon keeps a sideband on the call.
    await realtime.opened_sideband()
    with pytest.raises(VoiceCallError, match="already on"):
        await client.voice_calls.start(THREAD, "another offer")
    assert await client.voice_calls.end("rtc_1")
    assert realtime.hung_up == ["rtc_1"]
    assert not await client.voice_calls.end("rtc_unknown")


async def test_a_call_needs_a_key_a_conversation_and_openai(client, service):
    fake = FakeRealtime()
    service.realtime = fake
    with pytest.raises(VoiceCallError, match="OpenAI API key"):
        await client.voice_calls.start(THREAD, "offer")
    await service.set_voice_call_key(GOOD_KEY)
    with pytest.raises(VoiceCallError, match="Open a conversation"):
        await client.voice_calls.start(await service.inbox_thread("owner"), "offer")
    fake.refusal = "OpenAI refused: no access to the model"
    with pytest.raises(RealtimeError, match="no access"):
        await client.voice_calls.start(THREAD, "offer")


async def test_the_key_is_set_from_the_app_and_checked(client, service):
    service.realtime = FakeRealtime()
    assert (await client.voice_calls.settings()).key_source == ""
    with pytest.raises(VoiceKeyError):
        await client.voice_calls.set_key("sk-bad")
    assert (await client.voice_calls.set_key(GOOD_KEY)).key_source == "saved"
    assert (await client.voice_calls.remove_key()).key_source == ""


async def test_the_voices_tool_call_runs_through_the_assistant_and_lands_in_the_conversation(
    service, script, realtime, calls
):
    await calls.start("owner", THREAD, "offer")
    sideband = await realtime.opened_sideband()
    script.reply("It's sunny and 24°C.")
    sideband.say(*user_said("u1", "what's the weather?"), asked("call_1", "What's the weather now?"))
    output = (await sideband.sent_of("conversation.item.create"))[0]["item"]
    assert output == {"type": "function_call_output", "call_id": "call_1", "output": "It's sunny and 24°C."}
    # Then the voice is asked to answer with it.
    await sideband.sent_of("response.create")
    sideband.say(*voice_said("v1", "It's sunny, twenty-four degrees."))
    after = service.bus.last_id
    await calls.end("rtc_1")
    await _ended(service, after, THREAD)
    shown = [(m.role, m.text, m.voice) for m in await service.conversation_messages(THREAD)]
    assert shown == [
        ("user", "what's the weather?", "said"),
        ("user", "What's the weather now?", "asked"),
        ("assistant", "It's sunny and 24°C.", ""),
        ("assistant", "It's sunny, twenty-four degrees.", "said"),
    ]
    # The assistant heard what the user said in the call with the request.
    assert "User: what's the weather?" in script.requests[0][-1].text


async def test_a_tool_call_made_again_gets_the_first_result_without_asking_again(service, script, realtime, calls):
    await calls.start("owner", THREAD, "offer")
    sideband = await realtime.opened_sideband()
    script.reply("Done: the lights are off.")
    sideband.say(asked("call_7", "Turn off the lights"))
    first = (await sideband.sent_of("conversation.item.create"))[0]
    # The same call again, as after the sideband dropped and the event came again.
    sideband.say(asked("call_7", "Turn off the lights"))
    again = (await sideband.sent_of("conversation.item.create", 2))[1]
    assert first == again and first["item"]["output"] == "Done: the lights are off."
    assert len(script.requests) == 1
    await calls.end("rtc_1")


async def test_a_sideband_that_drops_is_opened_again(service, script, realtime, calls, monkeypatch):
    monkeypatch.setattr(voice_calls, "_RECONNECT_SECONDS", 0)
    await calls.start("owner", THREAD, "offer")
    first = await realtime.opened_sideband()
    first.say(SidebandLostError("gone"))
    second = await realtime.opened_sideband(2)
    script.reply("Yes.")
    second.say(asked("call_2", "Is it on?"))
    assert (await second.sent_of("conversation.item.create"))[0]["item"]["output"] == "Yes."
    await calls.end("rtc_1")


async def test_what_the_assistant_didnt_hear_goes_with_the_next_message(service, script, realtime, calls):
    await calls.start("owner", THREAD, "offer")
    sideband = await realtime.opened_sideband()
    sideband.say(*user_said("u1", "remind me to call mom"), *voice_said("v1", "I'll let the assistant know."))
    after = service.bus.last_id
    sideband.incoming.put_nowait(None)
    await _ended(service, after, THREAD)
    await collect(service.send(Session("owner", "web", THREAD), "did you get that?"))
    assert "User: remind me to call mom" in script.requests[-1][-1].text


async def test_the_daemon_hangs_up_its_calls_when_it_stops(service, realtime, calls):
    await calls.start("owner", THREAD, "offer")
    sideband = await realtime.opened_sideband()
    sideband.say(*user_said("u1", "bye"))
    stop = asyncio.Event()
    running = asyncio.create_task(calls.run(stop))
    stop.set()
    await running
    assert realtime.hung_up == ["rtc_1"]
    # What was said is kept before it's done.
    assert [m.text for m in await service.conversation_messages(THREAD)] == ["bye"]


async def test_the_voice_is_picked_from_the_app_and_the_next_call_speaks_in_it(client, realtime):
    with pytest.raises(VoiceChoiceError):
        await client.voice_calls.set_voice("robot")
    assert (await client.voice_calls.set_voice("sage")).voice == "sage"
    await client.voice_calls.start(THREAD, "offer")
    assert realtime.calls[0][2]["audio"]["output"]["voice"] == "sage"
    await client.voice_calls.end("rtc_1")
