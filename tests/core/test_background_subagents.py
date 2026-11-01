"""Background subagents: delegate(..., background=True) sends one off to work while the conversation goes on, with no
step limit; its answer goes back to the conversation when it ends, an approval pauses only it, and the user can stop
one. It goes on from where it stopped when the daemon starts again."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from langchain_core.messages import ToolMessage

from assistant.core import notifications
from assistant.core.agent import AssistantService, Session, SubagentError
from assistant.core.approvals import RemoteApprovals
from assistant.core.background_subagents import records
from assistant.core.config import settings
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.conversation import ended, queued
from assistant.core.events import Done, ToolFinished
from tests.conftest import collect


@asynccontextmanager
async def _working(service: AssistantService) -> AsyncIterator[None]:
    """The daemon's supervised task, started once the conversation's run sent them off, so the scripted model answers
    the run first."""
    stop = asyncio.Event()
    running = asyncio.create_task(service.background_subagents.run(stop))
    try:
        yield
    finally:
        stop.set()
        await running


async def _status(service: AssistantService, after: int, status: str) -> dict[str, Any]:
    """The next `subagents` event with that status after `after`."""
    async with asyncio.timeout(10):
        async for event in service.bus.subscribe(after):
            if event.kind == "subagents" and event.data["status"] == status:
                return event.data
    raise AssertionError("the bus stopped")


async def _sent_off(service: AssistantService, script, task: str = "dig") -> tuple[Session, str]:
    """A conversation whose reply sent a subagent off; its id."""
    session = Session("owner", "web", await service.new_thread("owner"))
    script.call("delegate", task=task, background=True).reply("Sent it off.")
    events = await collect(service.send(session, "dig into it"))
    sent = next(e for e in events if isinstance(e, ToolFinished) and e.name == "delegate")
    assert sent.output.startswith("Sent off as background subagent ") and isinstance(events[-1], Done)
    [subagent] = await service.background_subagents_of(session.thread_id)
    return session, subagent.id


def _results(request) -> list[str]:
    return [m.text for m in request if isinstance(m, ToolMessage)]


async def test_its_answer_goes_back_to_the_conversation_that_sent_it_off(service, script):
    session, subagent_id = await _sent_off(service, script)
    script.call("bash", command="echo 42").reply("The answer is 42.")
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "done")
    details = await service.subagent_details(subagent_id)
    assert (details.subagent.status, details.subagent.result) == ("done", "The answer is 42.")
    assert [(s.name, s.args, s.output, s.done) for s in details.steps] == [
        ("bash", {"command": "echo 42"}, "exit code: 0\n42\n", True)
    ]
    # The assistant follows it up at once, with its whole answer in the turn header note.
    assert await queued.threads(service.store, "owner") == [session.thread_id]
    [note] = await ended.take(service.store, "owner", session.thread_id)
    assert (
        f'The background subagent {subagent_id}, asked "dig", is done. Its answer:\nThe answer is 42.' in note["text"]
    )
    [feed] = await notifications.recent(service.store, "owner")
    assert feed.text == "✅ A subagent finished (dig): The answer is 42." and feed.thread_id == session.thread_id


async def test_it_has_no_step_limit(service, script, monkeypatch):
    monkeypatch.setattr(settings, "subagent_max_steps", 1)
    _, subagent_id = await _sent_off(service, script)
    script.call("bash", command="echo 1").call("bash", command="echo 2").call("bash", command="echo 3")
    script.reply("Three steps.")
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "done")
    details = await service.subagent_details(subagent_id)
    assert details.subagent.result == "Three steps." and details.subagent.steps == 3


async def test_an_approval_pauses_only_the_subagent(service, script):
    session, subagent_id = await _sent_off(service, script)
    script.call("bash", command="rm -rf build")
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "waiting")
        [subagent] = await service.background_subagents_of(session.thread_id)
        [asked] = subagent.waiting
        assert asked.request["command"] == "rm -rf build"
        # The conversation goes on meanwhile.
        script.reply("Still here.")
        events = await collect(service.send(session, "anything else?"))
        assert isinstance(events[-1], Done) and await service.pending_approvals(session.thread_id) == []
        script.reply("Left it.")
        after = service.bus.last_id
        assert await service.answer_subagent(subagent_id, asked.interrupt_id, {"approved": False, "reason": "no"})
        await _status(service, after, "done")
    assert "The user rejected this (no)." in _results(script.requests[-1])
    assert not await service.answer_subagent(subagent_id, asked.interrupt_id, {"approved": True})


async def test_an_approval_goes_to_the_chat_channel_its_conversation_is_on(service, script):
    forwarded: list[tuple[str, str]] = []

    class _Forwarder:
        async def forward(self, interrupt_id: str, title: str, request: dict[str, Any]) -> None:
            forwarded.append((interrupt_id, title))

    service.approvals.register("web", _Forwarder())
    service.approvals.register("telegram", _Forwarder())
    _, subagent_id = await _sent_off(service, script, task="clean up")
    script.call("bash", command="rm -rf build")
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "waiting")
        [subagent] = await service.background_subagents_of()
        await _until(lambda: forwarded)
        assert forwarded == [(subagent.waiting[0].interrupt_id, "The subagent working on “clean up”")]
        await service.stop_subagent(subagent_id)


async def test_the_user_can_stop_one_and_the_assistant_is_told_without_a_follow_up(service, script):
    session, subagent_id = await _sent_off(service, script)
    script.call("bash", command="rm -rf build")
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "waiting")
        stopped = await service.stop_subagent(subagent_id)
        assert stopped.status == "stopped" and stopped.waiting == []
        with pytest.raises(SubagentError):
            await service.stop_subagent(subagent_id)
    assert await queued.threads(service.store, "owner") == []
    [note] = await ended.take(service.store, "owner", session.thread_id)
    assert "is stopped: the user stopped it before it answered" in note["text"]
    await service.remove_subagent(subagent_id)
    assert await service.background_subagents_of(session.thread_id) == []


async def test_one_that_was_working_goes_on_when_the_daemon_starts_again(service, script):
    _, subagent_id = await _sent_off(service, script)
    script.call("bash", command="echo first").call("bash", command="rm -rf build")
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "waiting")
    # Stopped with the daemon, it's still waiting, and asks again.
    assert (await service.subagent_details(subagent_id)).subagent.status == "waiting"
    asked = len(script.requests)
    script.reply("Removed it.")
    after = service.bus.last_id
    async with _working(service):
        # Asked again: its answer is awaited where the apps answer it.
        await _until(lambda: service.approvals._waiting)
        [question] = (await service.subagent_details(subagent_id)).subagent.waiting
        await service.answer_subagent(subagent_id, question.interrupt_id, {"approved": True})
        await _status(service, after, "done")
    # Only the model call after the approval: nothing before it ran again.
    assert len(script.requests) == asked + 1
    details = await service.subagent_details(subagent_id)
    assert details.subagent.result == "Removed it." and [s.name for s in details.steps] == ["bash", "bash"]
    assert all(s.done for s in details.steps)


async def _until(condition) -> None:
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("never happened")


async def test_a_failure_is_told_as_a_warning(service, script):
    _, subagent_id = await _sent_off(service, script)
    script.refuse(RuntimeError("the model is down"))
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "failed")
    subagent = (await service.subagent_details(subagent_id)).subagent
    assert subagent.result == "RuntimeError: the model is down"
    [feed] = await notifications.recent(service.store, "owner")
    assert not feed.ok and feed.text == "⚠️ A subagent failed (dig): RuntimeError: the model is down"


async def test_deleting_the_conversation_stops_and_forgets_them(service, script, titles):
    session, subagent_id = await _sent_off(service, script)
    await asyncio.gather(*service._background)
    script.call("bash", command="rm -rf build")
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "waiting")
        await service.delete_conversation("owner", session.thread_id)
        assert await records.load(service.store, subagent_id) is None
    assert await notifications.recent(service.store, "owner") == []


async def test_a_scheduled_run_waits_for_its_subagent(service, script):
    script.call("delegate", task="x", background=True).reply("found it").reply("ok")
    events = await collect(service.send(Session("owner", UNATTENDED_CHANNEL, "job:x:1"), "go"))
    assert ToolFinished("delegate", "found it") in events
    assert await service.background_subagents_of() == []


async def test_an_unknown_named_subagent_isnt_sent_off(service, script):
    session = Session("owner", "web", await service.new_thread("owner"))
    script.call("delegate", task="x", agent="nobody", background=True).reply("ok")
    events = await collect(service.send(session, "go"))
    assert next(e for e in events if isinstance(e, ToolFinished)).output.startswith("Not delegated: No subagent named")
    assert await service.background_subagents_of() == []


async def test_waiting_with_no_time_limit_is_answered_from_the_apps():
    approvals = RemoteApprovals()
    waiting = asyncio.create_task(approvals.wait("i1", "a subagent", {"command": "ls"}))
    await asyncio.sleep(0)
    assert approvals.answer("i1", {"approved": True})
    assert await waiting == {"approved": True}
    assert not approvals.answer("i1", {"approved": True})


async def test_two_approvals_at_once_are_each_answered_in_turn(service, script):
    _, subagent_id = await _sent_off(service, script)
    script.reply(
        tool_calls=[
            {"name": "bash", "args": {"command": "rm -rf a"}, "id": "c-a"},
            {"name": "bash", "args": {"command": "rm -rf b"}, "id": "c-b"},
        ]
    ).reply("Both done.")
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "waiting")
        await _until(lambda: len(service.approvals._waiting) == 2)
        first_one, second = (await service.subagent_details(subagent_id)).subagent.waiting
        assert await service.answer_subagent(subagent_id, first_one.interrupt_id, {"approved": False, "reason": "no"})
        await _until_left(service, subagent_id, [second.interrupt_id])
        after = service.bus.last_id
        assert await service.answer_subagent(subagent_id, second.interrupt_id, {"approved": False, "reason": "no"})
        await _status(service, after, "done")


async def _until_left(service: AssistantService, subagent_id: str, left: list[str]) -> None:
    async with asyncio.timeout(10):
        while [w.interrupt_id for w in (await service.subagent_details(subagent_id)).subagent.waiting] != left:
            await asyncio.sleep(0.01)


async def test_a_deleted_conversation_gets_no_new_subagent(service, script):
    session, _ = await _sent_off(service, script)
    script.call("bash", command="rm -rf build")
    after = service.bus.last_id
    async with _working(service):
        await _status(service, after, "waiting")
        await service.delete_conversation("owner", session.thread_id)
        assert await service.background_subagents_of(session.thread_id) == []
        with pytest.raises(SubagentError):
            await service.background_subagents.start("x", "owner", session.thread_id, "web", [])
