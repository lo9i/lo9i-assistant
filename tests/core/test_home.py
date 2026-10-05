"""The home conversation and side conversations: the agent suggests moving a focused task out of
home, and the run waits for the user's answer like for an approval."""

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
