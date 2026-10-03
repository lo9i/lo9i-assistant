"""Getting to know the user: the one-time offer after setup, and the built-in skills it uses."""

from assistant.core.agent import Session
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.memory import profile
from assistant.core.memory.profile import Profile
from assistant.core.skills import store
from tests.conftest import collect

_OFFER = "[Note for you, not from the user:]"


def _note_sent(script) -> bool:
    return any(_OFFER in b.get("text", "") for b in script.requests[-1][-1].content)


async def test_the_first_message_with_an_empty_profile_carries_the_offer_once(service, script):
    session = await service.session("owner", "cli")
    script.reply("Hi!")
    await collect(service.send(session, "hello"))
    assert _note_sent(script) and "get-to-know-you" in script.requests[-1][-1].content[1]["text"]
    script.reply("Sure.")
    await collect(service.send(session, "and now?"))
    assert not _note_sent(script)
    shown = await service.conversation_messages(session.thread_id)
    assert [m.text for m in shown if m.role == "user"] == ["hello", "and now?"]


async def test_a_filled_profile_means_no_offer_ever(service, script):
    await profile.save(service.store, "owner", Profile(about=["Ana, Madrid"]))
    script.reply("Hi!")
    await collect(service.send(await service.session("owner", "cli"), "hello"))
    assert not _note_sent(script)
    await profile.save(service.store, "owner", Profile())
    script.reply("Hi again!")
    await collect(service.send(await service.session("owner", "cli"), "hello again"))
    assert not _note_sent(script)


async def test_a_scheduled_run_doesnt_use_up_the_offer(service, script):
    script.reply("Done.")
    await collect(service.send(Session("owner", UNATTENDED_CHANNEL, "job:x:1"), "check the news"))
    assert not _note_sent(script)
    script.reply("Hi!")
    await collect(service.send(await service.session("owner", "cli"), "hello"))
    assert _note_sent(script)


def test_the_skills_are_built_in_and_complete():
    found = {s.name: s for s in store.list_skills()}
    for name in ("get-to-know-you", "people-lookup"):
        assert found[name].builtin and not found[name].problems
    assert "people-lookup" in found["get-to-know-you"].instructions
