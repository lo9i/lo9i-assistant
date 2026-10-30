"""While an update installs, runs are kept instead of refused (core/conversation/held.py): a message with its files,
an answer to an approval. Each runs later as it would have then, in the order it came, once and only once."""

import asyncio

from assistant.core.agent import Session
from assistant.core.attachments import Attachment
from assistant.core.conversation.held import CHAT, Origin
from assistant.core.events import ApprovalRequired, Done, Held, ToolFinished
from tests.conftest import collect


async def _held(service, events) -> Held:
    [held] = await collect(events)
    assert isinstance(held, Held)
    return held


async def test_a_message_sent_while_runs_are_held_is_kept_with_its_files_and_runs_later(service, script):
    session = Session("owner", "telegram", await service.new_thread("owner"), Origin(CHAT, {"chat": "42"}))
    await service.hold_runs()
    note = Attachment("notes.txt", "text/plain", b"buy milk")
    held = await _held(service, service.send(session, "read this", [note]))
    assert script.requests == []  # nothing ran
    [kept] = await service.held_runs("owner")
    assert (kept.id, kept.thread_id, kept.channel, kept.text) == (held.id, session.thread_id, "telegram", "read this")
    assert kept.origin == Origin(CHAT, {"chat": "42"})

    service.release_runs()
    script.reply("Milk it is.")
    assert isinstance((await collect(service.run_held(session, kept)))[-1], Done)
    request = script.requests[0][-1]
    assert "read this" in request.text and "buy milk" in str(request.content)
    shown = [(m.role, m.text) for m in await service.conversation_messages(session.thread_id)]
    assert shown == [("user", "[attachment notes.txt]\nread this"), ("assistant", "Milk it is.")]
    assert await service.held_runs("owner") == []
    await asyncio.gather(*service._background)


async def test_held_runs_wait_in_the_order_they_came_and_each_runs_once(service, script):
    first = Session("owner", "web", await service.new_thread("owner"))
    second = Session("owner", "web", await service.new_thread("owner"))
    await service.hold_runs()
    await _held(service, service.send(second, "one"))
    await _held(service, service.send(first, "two"))
    kept = await service.held_runs("owner")
    assert [k.text for k in kept] == ["one", "two"]
    # Held again (an unfinished update going back at start): still kept, not kept twice.
    await _held(service, service.run_held(second, kept[0]))
    assert [k.text for k in await service.held_runs("owner")] == ["one", "two"]

    service.release_runs()
    script.reply("One.")
    await collect(service.run_held(second, kept[0]))
    assert await collect(service.run_held(second, kept[0])) == []  # it ran already
    assert len(script.requests) == 1


async def test_an_answer_to_an_approval_sent_while_runs_are_held_answers_it_later(service, script):
    script.call("bash", command="rm -rf build").reply("Removed.")
    session = Session("owner", "web", await service.new_thread("owner"))
    events = await collect(service.send(session, "clean up"))
    approval = next(e for e in events if isinstance(e, ApprovalRequired))
    await service.hold_runs()
    await _held(service, service.resume(session, {approval.interrupt_id: {"approved": False, "reason": "not now"}}))
    service.release_runs()
    [kept] = await service.held_runs("owner")
    events = await collect(service.run_held(session, kept))
    assert events[0] == ToolFinished("bash", "The user rejected this (not now).") and isinstance(events[-1], Done)
