"""Renaming the assistant: the name enters the system prompt at the next message, with nothing
summarized away."""

from assistant.core import identity
from tests.conftest import collect


async def _say(service, text):
    await collect(service.send(await service.session("owner", "cli"), text))


async def test_rename_by_asking_rebuilds_the_prompt_at_the_next_message(service, script, summaries):
    script.reply("hello").call("rename_assistant", name="  Max ").reply("Call me Max!").reply("I'm Max.")
    await _say(service, "hi")
    await _say(service, "call yourself Max")
    assert await identity.load_name(service.store) == "Max"
    assert "Your name is" not in script.requests[-1][0].content  # same epoch until the next message
    await _say(service, "who are you?")
    prompt, *messages = script.requests[-1]
    assert "Your name is Max." in prompt.content
    # hi, hello, call yourself Max, the tool call, its result, Call me Max!, who are you?
    assert len(messages) == 7 and summaries.inputs == []  # every message kept, nothing summarized


async def test_invalid_names_are_refused(service, script):
    script.call("rename_assistant", name="   ").reply("ok")
    events = await collect(service.send(await service.session("owner", "cli"), "rename"))
    assert events[1].output == "The name can't be empty."
    assert await identity.load_name(service.store) == ""
