"""Sending messages, tool calls, approvals and conversations shared across channels."""

from assistant.core.events import ApprovalRequired, Done, ToolFinished, ToolStarted
from tests.conftest import collect


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


async def test_new_message_while_approval_pending_repeats_the_approval(service, script):
    script.call("bash", command="rm -rf build")
    session = await service.session("u", "cli")
    await collect(service.send(session, "clean up"))
    again = await collect(service.send(session, "hello?"))
    assert len(again) == 1 and isinstance(again[0], ApprovalRequired)


async def test_bash_runs_in_the_workspace_without_app_secrets(service, script, monkeypatch, isolated_settings):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    script.call("bash", command="pwd; env | grep -c KEY || true").reply("ok")
    events = await collect(service.send(await service.session("u", "cli"), "where am I"))
    output = events[1].output
    assert str(isolated_settings / "workspace") in output and output.strip().endswith("0")


async def test_channels_share_home_until_their_new_and_go_back_with_home(service):
    home = await service.home_thread("u")
    assert (await service.session("u", "telegram")).thread_id == home
    assert (await service.session("u", "slack")).thread_id == home
    side = await service.new_channel_thread("u", "telegram")
    assert side != home and (await service.session("u", "telegram")).thread_id == side
    assert (await service.session("u", "slack")).thread_id == home
    assert await service.channel_home("u", "telegram") == home
    assert (await service.session("u", "telegram")).thread_id == home


async def test_deleting_home_starts_a_new_one(service, script):
    home = await service.home_thread("u")
    await collect(service.send(await service.session("u", "telegram"), "hi"))
    await service.delete_conversation("u", home)
    assert await service.home_thread("u") not in {home, ""}


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


async def test_channels_on_a_conversation_from_before_home_move_there_once(service):
    namespace = ("threads", "u")
    await service._storage.store.aput(namespace, "telegram", {"thread_id": "u:old"})
    assert await service.channels_to_home("u") == 1
    home = (await service.session("u", "telegram")).thread_id
    assert home != "u:old" and home == await service.home_thread("u")
    side = await service.new_channel_thread("u", "telegram")
    assert await service.channels_to_home("u") == 0
    assert (await service.session("u", "telegram")).thread_id == side
