"""The home conversation and side conversations: the agent suggests moving a focused task out of
home, and the run waits for the user's answer like for an approval."""

import asyncio

from assistant.core.agent import Session
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.events import ApprovalRequired, Done, ToolFinished, is_side_conversation
from tests.conftest import collect


async def _suggested(service, script):
    script.call("suggest_side_conversation", title="Tax return", brief="Fill in the 2026 return.").reply("Moved.")
    session = await service.session("u", "web")
    events = await collect(service.send(session, "let's do my taxes"))
    return session, next(e for e in events if isinstance(e, ApprovalRequired))


async def test_a_suggestion_in_home_waits_and_carries_the_brief(service, script):
    session, asked = await _suggested(service, script)
    assert is_side_conversation(asked.request)
    assert asked.request["first_message"] == "Carried over from home: Tax return\n\nFill in the 2026 return."
    events = await collect(service.resume(session, {asked.interrupt_id: {"moved": True}}))
    assert events[0].output.startswith("The user moved this to a side conversation, 'Tax return'")
    assert isinstance(events[-1], Done)


async def test_declining_keeps_the_task_in_home(service, script):
    session, asked = await _suggested(service, script)
    events = await collect(service.resume(session, {asked.interrupt_id: {"moved": False}}))
    assert events[0] == ToolFinished("suggest_side_conversation", "The user wants to keep working on it here.")


async def test_its_not_suggested_outside_home(service, script):
    script.call("suggest_side_conversation", title="x", brief="y").reply("ok")
    side = Session("u", "web", await service.new_thread("u"))
    events = await collect(service.send(side, "go"))
    assert ToolFinished("suggest_side_conversation", "Not suggested: this is already a side conversation.") in events
    script.call("suggest_side_conversation", title="x", brief="y").reply("ok")
    events = await collect(service.send(Session("u", UNATTENDED_CHANNEL, "job:x:1"), "go"))
    assert ToolFinished("suggest_side_conversation", "Not suggested: nobody is watching this scheduled run.") in events


async def test_home_is_listed_first(service, script):
    await collect(service.send(await service.session("u", "telegram"), "hi"))
    await collect(service.send(Session("u", "web", await service.new_thread("u")), "later"))
    listed = await service.list_conversations("u")
    assert [c.home for c in listed] == [True, False] and listed[0].thread_id == await service.home_thread("u")


async def _with_a_side_conversation(service, script, titles) -> str:
    """A side conversation about the taxes, and home started."""
    titles.title, titles.tags = "The 2026 tax return", ["taxes", "tax return"]
    script.reply("Let's start.").reply("Hi.")
    side = Session("u", "web", await service.new_thread("u"))
    await collect(service.send(side, "Help me with my 2026 tax return. I have the forms."))
    await asyncio.gather(*service._background)
    await collect(service.send(await service.session("u", "web"), "hi"))
    return side.thread_id


async def test_a_message_in_home_names_the_side_conversations_it_may_continue(service, script, titles):
    side = await _with_a_side_conversation(service, script, titles)
    script.reply("ok").reply("ok")
    await collect(service.send(await service.session("u", "web"), "how is my tax return going?"))
    note = _header_text(script.requests[-1][-1])
    assert f"- {side}: " in note and "It began: Help me with my 2026 tax return. I have the forms." in note
    await collect(service.send(Session("u", "web", side), "what about the tax forms?"))
    assert "These side conversations" not in _header_text(script.requests[-1][-1])


def _header_text(message) -> str:
    return " ".join(b.get("text", "") for b in message.content if isinstance(b, dict))


async def test_continuing_a_side_conversation_names_it(service, script, titles):
    side = await _with_a_side_conversation(service, script, titles)
    script.call("suggest_side_conversation", title="Taxes", brief="Go on.", continue_in=side).reply("Moved.")
    session = await service.session("u", "web")
    events = await collect(service.send(session, "back to my taxes"))
    asked = next(e for e in events if isinstance(e, ApprovalRequired))
    assert asked.request["thread_id"] == side
    assert asked.request["first_message"] == "Carried over from home: Taxes\n\nGo on."
    events = await collect(service.resume(session, {asked.interrupt_id: {"moved": True}}))
    assert events[0].output.startswith("The user moved this back to the side conversation")


async def test_continuing_an_unknown_conversation_asks_nothing(service, script, titles):
    await _with_a_side_conversation(service, script, titles)
    script.call("suggest_side_conversation", title="Taxes", brief="Go on.", continue_in="u:nope").reply("ok")
    events = await collect(service.send(await service.session("u", "web"), "back to my taxes"))
    assert ToolFinished("suggest_side_conversation", "No side conversation u:nope.") in events
