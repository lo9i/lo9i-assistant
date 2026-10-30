"""The inbox: where a message written outside a conversation goes to be routed. The assistant moves work
that outgrows a quick answer out of it without asking, conversations are listed newest first with the
inbox marked, and the home conversation from before the inbox is kept as an archived conversation."""

import asyncio

import pytest

from assistant.core import conversations, inbox
from assistant.core.agent import HandoffError, Session
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.conversation.dispatch import FOLLOW_UP, QUICK, Pick
from assistant.core.events import ApprovalRequired, Dispatched, ToolFinished
from tests.conftest import collect
from tests.core.test_handoffs import agent_plugin


async def test_work_that_outgrows_the_inbox_moves_to_a_new_conversation_as_the_user_wrote_it(service, script):
    script.call("move_to_conversation").reply("Moved.")
    session = await service.session("u", "web")
    events = await collect(service.send(session, "let's do my taxes"))
    assert not [e for e in events if isinstance(e, ApprovalRequired)]
    moved = next(e for e in events if isinstance(e, Dispatched))
    assert (moved.thread_id, moved.title, moved.text, moved.carried) == (
        "",
        "New conversation",
        "let's do my taxes",
        "",
    )
    assert moved.line == "→ Started a new conversation."
    finished = next(e for e in events if isinstance(e, ToolFinished))
    assert finished.output.startswith("Moved the user's message to a new conversation")
    script.reply("Let's start.")
    new = Session("u", "web", await service.new_thread("u"))
    await collect(service.send_dispatched(new, moved.id))
    first, reply = await service.conversation_messages(new.thread_id)
    assert (first.role, first.text) == ("user", "let's do my taxes")  # their own words, nothing written for them
    assert (reply.role, reply.text) == ("assistant", "Let's start.")


async def test_a_quick_exchange_moved_goes_with_the_message_and_the_inbox_starts_afresh(service, script, inbox_answers):
    inbox_answers.picks.extend([Pick(QUICK, 0.9, ""), Pick(FOLLOW_UP, 0.9, "")])
    session = await service.session("u", "web")
    script.reply("150 km.")
    await collect(service.send(session, "how far is Rome from Florence?"))
    script.call("move_to_conversation").reply("Moved.")
    events = await collect(service.send(session, "ok, plan the whole trip"))
    moved = next(e for e in events if isinstance(e, Dispatched))
    assert moved.text == "ok, plan the whole trip" and "with the quick exchange" in moved.line
    assert moved.carried.startswith("**You:** how far is Rome from Florence?")
    script.reply("Here's the plan.")
    new = Session("u", "web", await service.new_thread("u"))
    await collect(service.send_dispatched(new, moved.id))
    assert "User: how far is Rome from Florence?" in str(script.requests[-1][-1].content)
    carried_shown, first = (await service.conversation_messages(new.thread_id))[:2]
    assert (carried_shown.role, first.role, first.text) == ("carried", "user", "ok, plan the whole trip")
    script.reply("Sure.")
    await collect(service.send(session, "what time is it in Tokyo?"))
    assert inbox_answers.exchanges[-1] == ""  # the moved exchange isn't the inbox's any more


async def test_its_not_moved_outside_the_inbox(service, script):
    script.call("move_to_conversation").reply("ok")
    side = Session("u", "web", await service.new_thread("u"))
    events = await collect(service.send(side, "go"))
    assert ToolFinished("move_to_conversation", "Not moved: this is already a conversation of its own.") in events
    script.call("move_to_conversation").reply("ok")
    events = await collect(service.send(Session("u", UNATTENDED_CHANNEL, "job:x:1"), "go"))
    assert ToolFinished("move_to_conversation", "Not moved: nobody is watching this scheduled run.") in events


async def test_conversations_are_listed_newest_first_with_the_inbox_marked(service, script):
    await collect(service.send(await service.session("u", "telegram"), "hi"))
    await collect(service.send(Session("u", "web", await service.new_thread("u")), "later"))
    listed = await service.list_conversations("u")
    assert [c.inbox for c in listed] == [False, True] and listed[1].thread_id == await service.inbox_thread("u")


async def test_the_home_conversation_is_kept_as_an_archived_one(service, script, titles, digests):
    script.reply("Hi.").reply("Noted.")
    home = Session("u", "telegram", await service.new_thread("u"))
    await collect(service.send(home, "hello from before the inbox"))
    await collect(service.send(home, "I moved to Lisbon"))
    await service.store.aput(("home", "u"), "thread_id", {"thread_id": home.thread_id})
    await service.store.aput(inbox.channels_namespace("u"), "telegram", {"thread_id": home.thread_id})
    assert await service.retire_home("u") == home.thread_id
    await asyncio.gather(*service._background)
    retired = await conversations.load(service.store, "u", home.thread_id)
    assert retired is not None and retired.archived and retired.title == "Home (before the inbox)"
    assert [m.text for m in await service.conversation_messages(home.thread_id)][:2] == [
        "hello from before the inbox",
        "Hi.",
    ]
    await service.memory_writer.write_all()
    assert "Lisbon" in digests.inputs[0].transcript  # what's new in it goes to memory
    assert await service.channel_thread("u", "telegram") == await service.inbox_thread("u")
    assert await service.retire_home("u") is None


async def test_the_inbox_cant_be_handed_to_an_agent(service, tmp_path):
    await service.add_mcp_server(agent_plugin())
    with pytest.raises(HandoffError, match="can't be handed over"):
        await service.hand_conversation("u", await service.inbox_thread("u"), "claude", str(tmp_path))
