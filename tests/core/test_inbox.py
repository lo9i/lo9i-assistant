"""The inbox: where a message written outside a conversation goes to be routed. The assistant moves work
that outgrows a quick answer out of it without asking, conversations are listed newest first with the
inbox marked, and the home conversation from before the inbox is kept as an archived conversation."""

import asyncio

import pytest

from assistant.core import conversations, inbox
from assistant.core.agent import HandoffError, Session
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.events import ApprovalRequired, Dispatched, ToolFinished
from tests.conftest import collect
from tests.core.test_handoffs import agent_plugin


async def test_work_that_outgrows_the_inbox_moves_to_a_new_conversation_without_asking(service, script):
    script.call("move_to_conversation", title="Tax return", brief="Fill in the 2026 return.").reply("Moved.")
    session = await service.session("u", "web")
    events = await collect(service.send(session, "let's do my taxes"))
    assert not [e for e in events if isinstance(e, ApprovalRequired)]
    moved = next(e for e in events if isinstance(e, Dispatched))
    assert (moved.thread_id, moved.title) == ("", "Tax return")
    assert moved.text == "Carried over from the inbox: Tax return\n\nFill in the 2026 return."
    finished = next(e for e in events if isinstance(e, ToolFinished))
    assert finished.output.startswith("Moved this to a new conversation, 'Tax return'")
    script.reply("Let's start.")
    new = Session("u", "web", await service.new_thread("u"))
    await collect(service.send_dispatched(new, moved.id))
    assert (await service.conversation_messages(new.thread_id))[0].text == moved.text


async def test_its_not_moved_outside_the_inbox(service, script):
    script.call("move_to_conversation", title="x", brief="y").reply("ok")
    side = Session("u", "web", await service.new_thread("u"))
    events = await collect(service.send(side, "go"))
    assert ToolFinished("move_to_conversation", "Not moved: this is already a conversation of its own.") in events
    script.call("move_to_conversation", title="x", brief="y").reply("ok")
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
