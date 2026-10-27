"""Sending messages, tool calls, approvals and conversations shared across channels."""

import asyncio

from langchain_core.messages import ToolMessage

from assistant.core.events import MOVED_ON, ApprovalRequired, Done, Error, ToolFinished, ToolStarted
from tests.conftest import collect, written


async def test_safe_bash_runs_without_approval(service, script):
    script.call("bash", command="echo hello").reply("done")
    session = await service.session("u", "cli")
    events = await collect(service.send(session, "say hello"))
    assert [type(e) for e in events] == [ToolStarted, ToolFinished, Done]
    assert "hello" in events[1].output


async def test_dangerous_bash_waits_for_approval_and_rejection_reaches_the_model(service, script):
    script.call("bash", command="rm -rf build").reply("ok, left it")
    session = await service.session("u", "cli")
    events = await collect(service.send(session, "clean up"))
    approval = next(e for e in events if isinstance(e, ApprovalRequired))
    assert approval.request == {"tool": "bash", "command": "rm -rf build", "reason": "recursive delete"}

    events = await collect(service.resume(session, {approval.interrupt_id: {"approved": False, "reason": "no"}}))
    assert events[0] == ToolFinished("bash", "The user rejected this (no).")
    assert isinstance(events[-1], Done)


async def test_a_new_message_while_an_approval_waits_rejects_it_and_is_answered(service, script):
    script.call("bash", command="rm -rf build").reply("Hello!")
    session = await service.session("u", "cli")
    await collect(service.send(session, "clean up"))
    events = await collect(service.send(session, "hello?"))
    rejected = f"The user rejected this ({MOVED_ON})."
    assert events[0] == ToolFinished("bash", rejected) and isinstance(events[-1], Done)
    assert not any(isinstance(e, ApprovalRequired) for e in events)
    # The model reads the rejection and the new message together, in one call.
    assert len(script.requests) == 2
    last = script.requests[-1]
    assert isinstance(last[-2], ToolMessage) and last[-2].text == rejected and "hello?" in last[-1].text
    assert await service.pending_approvals(session.thread_id) == []


async def test_a_question_waiting_is_skipped_when_a_new_message_comes(service, script):
    script.call("ask_user", question="Which?", options=["A", "B"]).reply("Sure.")
    session = await service.session("u", "cli")
    await collect(service.send(session, "pick one"))
    events = await collect(service.send(session, "never mind"))
    assert isinstance(events[0], ToolFinished) and events[0].name == "ask_user" and isinstance(events[-1], Done)


async def test_bash_runs_in_the_workspace_without_app_secrets(service, script, monkeypatch, isolated_settings):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    script.call("bash", command="pwd; env | grep -c ANTHROPIC_API_KEY || true").reply("ok")
    events = await collect(service.send(await service.session("u", "cli"), "where am I"))
    output = events[1].output
    assert str(isolated_settings / "workspace") in output and output.strip().endswith("0")


async def test_channels_write_to_the_inbox_and_keep_where_their_last_message_went(service):
    inbox = await service.inbox_thread("u")
    assert (await service.session("u", "telegram")).thread_id == inbox
    assert await service.channel_thread("u", "telegram") == inbox
    side = await service.new_thread("u")
    await service.channel_wrote("u", "telegram", side)
    assert await service.channel_thread("u", "telegram") == side
    assert await service.channel_thread("u", "slack") == inbox
    assert (await service.session("u", "telegram")).thread_id == inbox


async def test_deleting_the_inbox_starts_a_new_one(service, script):
    inbox = await service.inbox_thread("u")
    await collect(service.send(await service.session("u", "telegram"), "hi"))
    await service.delete_conversation("u", inbox)
    assert await service.inbox_thread("u") not in {inbox, ""}


async def test_every_user_message_starts_with_a_turn_header(service, script):
    session = await service.session("u", "telegram")
    await collect(service.send(session, "hi"))
    header = script.requests[0][1].content[0]["text"]
    assert header.startswith("[") and header.endswith(", via telegram]")


async def test_unattended_runs_deny_instead_of_asking(service, script):
    from assistant.core.tools.approval import UNATTENDED_DENIAL

    script.call("bash", command="rm -rf build").reply("could not")
    events = await collect(service.send(await service.session("u", "worker"), "clean up"))
    assert not any(isinstance(e, ApprovalRequired) for e in events)
    assert events[1].output.startswith(UNATTENDED_DENIAL)


async def test_runs_are_held_off_once_none_is_in_progress_until_released(service, script, tmp_path):
    script.call("bash", command="echo up > a.started; until [ -f a ]; do sleep 0.02; done").reply("done").reply("hi")
    session = await service.session("u", "cli")
    running = asyncio.create_task(collect(service.send(session, "wait")))
    await written(tmp_path / "workspace" / "a.started")
    holding = asyncio.create_task(service.hold_runs("lo9i is installing an update."))
    await asyncio.sleep(0.05)
    assert not holding.done()  # it waits for the run in progress
    (tmp_path / "workspace" / "a").touch()
    await running
    await asyncio.wait_for(holding, 5)
    assert await collect(service.send(session, "hello")) == [Error("lo9i is installing an update.")]
    service.release_runs()
    assert isinstance((await collect(service.send(session, "hello")))[-1], Done)
