"""Skills pinned to a conversation: in full in its system prompt from the next user message on, with
nothing summarized away, and a note in that message's turn header."""

import pytest

from assistant.core.agent import Session
from assistant.core.skills import store
from assistant.core.skills.store import SkillError
from tests.conftest import collect


@pytest.fixture
def coding(isolated_settings, monkeypatch):
    monkeypatch.setattr("assistant.core.config.settings.skills_dir", str(isolated_settings / "skills"))
    store.save("coding", "Programming help", "Run the tests before saying it works.")


async def _say(service, session, text):
    await collect(service.send(session, text))


def _texts(message):
    return [block["text"] for block in message.content if block.get("type") == "text"]


async def test_a_pinned_skill_enters_the_prompt_at_the_next_message(service, script, summaries, coding):
    script.reply("hello").reply("pinned").reply("still")
    session = Session("owner", "cli", await service.new_thread("owner"))
    await _say(service, session, "hi")
    assert await service.pin_skill("owner", session.thread_id, "coding") == ["coding"]
    await _say(service, session, "fix this")
    prompt, *messages = script.requests[-1]
    assert "# Pinned skills" in prompt.content and "Run the tests before saying it works." in prompt.content
    assert len(messages) == 3 and summaries.inputs == []
    assert any("Pinned now: coding." in text for text in _texts(messages[-1]))
    await _say(service, session, "and this")
    prompt, *messages = script.requests[-1]
    assert "Run the tests before saying it works." in prompt.content
    assert not any("Pinned now" in text for text in _texts(messages[-1]))


async def test_unpinning_takes_the_skill_out_of_the_prompt(service, script, coding):
    script.reply("one").reply("two")
    session = Session("owner", "cli", await service.new_thread("owner"))
    await service.pin_skill("owner", session.thread_id, "coding")
    await _say(service, session, "hi")
    assert await service.unpin_skill("owner", session.thread_id, "coding") == []
    await _say(service, session, "plain now")
    prompt, *messages = script.requests[-1]
    assert "# Pinned skills" not in prompt.content
    assert any("Pinned now: none." in text for text in _texts(messages[-1]))


async def test_pins_belong_to_one_conversation(service, script, coding):
    first = Session("owner", "cli", await service.new_thread("owner"))
    await service.pin_skill("owner", first.thread_id, "coding")
    other = await service.new_thread("owner")
    assert await service.pinned_skills("owner", other) == []


async def test_unknown_skills_cant_be_pinned(service, coding):
    session = Session("owner", "cli", await service.new_thread("owner"))
    with pytest.raises(SkillError):
        await service.pin_skill("owner", session.thread_id, "nope")


async def test_a_deleted_skill_is_left_out_and_can_still_be_unpinned(service, script, coding):
    script.reply("ok")
    session = Session("owner", "cli", await service.new_thread("owner"))
    await service.pin_skill("owner", session.thread_id, "coding")
    store.delete("coding")
    await _say(service, session, "hi")
    assert "# Pinned skills" not in script.requests[-1][0].content
    assert await service.unpin_skill("owner", session.thread_id, "coding") == []


async def test_deleting_the_conversation_forgets_its_pins(service, script, coding):
    script.reply("ok")
    session = Session("owner", "cli", await service.new_thread("owner"))
    await _say(service, session, "hi")
    await service.pin_skill("owner", session.thread_id, "coding")
    await service.new_thread("owner")
    await service.delete_conversation("owner", session.thread_id)
    assert await service.pinned_skills("owner", session.thread_id) == []
