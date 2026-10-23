"""Conversations handed to a plugin's agent: each message runs as one of its tasks instead of the
assistant's model answering, both messages are kept, and the assistant hears about it when the user hands
the conversation back. The agent's worker is tests/core/fake_agent_worker.py."""

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from assistant.core.agent import AssistantService, FolderError, HandoffError, Session
from assistant.core.agent_tasks import workers
from assistant.core.agent_tasks.records import TaskStore
from assistant.core.attachments import Attachment
from assistant.core.events import Done, Error, TextDelta, ToolFinished, ToolStarted, UserSaid
from assistant.core.mcp import folders, servers
from assistant.core.mcp.servers import McpServer
from assistant.daemon.managers import ByHand
from assistant.daemon.shutdown import Ending, Shutdown
from tests.conftest import collect

WORKER = str(Path(__file__).with_name("fake_agent_worker.py"))


def agent_plugin(name: str = "claude-code", command: str = "claude", **fields) -> McpServer:
    return McpServer(
        name,
        agent_command=command,
        agent_name="Claude Code",
        agent_worker=sys.executable,
        agent_args=[WORKER],
        **fields,
    )


def asked(name: str = "claude-code") -> list[dict]:
    """The tasks the agent was given, oldest first."""
    records = sorted((folders.data(name) / "tasks").glob("*/task.json"), key=lambda p: p.stat().st_mtime_ns)
    return [json.loads(record.read_text()) for record in records]


@pytest.fixture
async def service(script, digests, summaries, titles) -> AsyncIterator[AssistantService]:
    async with AssistantService.open() as svc:
        await svc.add_mcp_server(agent_plugin())
        yield svc


async def _handed(service, tmp_path):
    session = Session("owner", "cli", await service.new_thread("owner"))
    await service.hand_conversation("owner", session.thread_id, "claude", str(tmp_path))
    return session


async def test_the_agent_answers_instead_of_the_assistant_and_both_messages_are_kept(service, script, tmp_path):
    assert [(a.command, a.name) for a in await service.agents()] == [("claude", "Claude Code")]
    session = await _handed(service, tmp_path)
    events = await collect(service.send(session, "fix the tests"))
    assert events == [TextDelta(f"Done in {tmp_path}: fix the tests"), Done()]
    assert [(t["repository"], t["prompt"]) for t in asked()] == [(str(tmp_path), "fix the tests")]
    assert script.requests == []  # the assistant's model wasn't asked
    shown = [(m.role, m.text) for m in await service.conversation_messages(session.thread_id)]
    assert shown[-2:] == [("user", "fix the tests"), ("assistant", f"Done in {tmp_path}: fix the tests")]


async def test_the_agents_thinking_text_and_tool_calls_are_shown_as_it_works(service, tmp_path):
    session = await _handed(service, tmp_path)
    events = await collect(service.send(session, "work out loud"))
    assert events == [
        TextDelta("The test expects a list."),  # its thinking reads as what it says
        TextDelta("\n\nRunning the tests."),
        ToolStarted("Bash", {"detail": "pytest -q"}, id="t1"),
        ToolFinished("Bash", "1 failed"),
        TextDelta("Fixed it."),
        TextDelta("\n\nAll green."),
        Done(),  # the reply, its last text, isn't shown twice
    ]
    shown = await service.conversation_messages(session.thread_id)
    assert [(m.role, m.text, m.detail, m.output) for m in shown[1:]] == [  # as shown live, after a reload
        ("assistant", "The test expects a list.\n\nRunning the tests.", "", ""),
        ("tool", "Bash", "pytest -q", "1 failed"),
        ("assistant", "Fixed it.\n\nAll green.", "", ""),
    ]
    _, *messages = (await service._graph.aget_state({"configurable": {"thread_id": session.thread_id}})).values[
        "messages"
    ]
    assert messages[-1].content == "All green."  # what the assistant's model reads when it gets the conversation back


async def test_a_reply_after_only_thinking_is_a_paragraph_of_the_same_message(service, tmp_path):
    session = await _handed(service, tmp_path)
    events = await collect(service.send(session, "think, then answer"))
    assert events == [TextDelta("Easy one."), TextDelta("\n\nFour."), Done()]
    shown = await service.conversation_messages(session.thread_id)
    assert [(m.role, m.text) for m in shown[1:]] == [("assistant", "Easy one.\n\nFour.")]


async def test_plain_lines_from_an_agent_are_shown_inside_a_call_named_after_it(service, tmp_path):
    session = await _handed(service, tmp_path)
    events = await collect(service.send(session, "show your steps"))
    call = events[0]
    assert isinstance(call, ToolStarted) and call.name == "Claude Code" and call.id
    steps = [(e.name, e.within) for e in events if isinstance(e, ToolStarted | ToolFinished) and e.within]
    assert steps == [(s, call.id) for s in ("Read: README.md", "Read: README.md", "Ran: pytest", "Ran: pytest")]
    assert events[-3:] == [
        ToolFinished("Claude Code", "Done"),
        TextDelta(f"Done in {tmp_path}: show your steps"),
        Done(),
    ]
    shown = [(m.role, m.text) for m in await service.conversation_messages(session.thread_id)]
    assert shown[1:] == [
        ("tool", "Read: README.md"),
        ("tool", "Ran: pytest"),
        ("assistant", f"Done in {tmp_path}: show your steps"),
    ]


async def test_handed_back_the_assistant_answers_and_hears_who_did_meanwhile(service, script, tmp_path):
    script.reply("I see Claude Code fixed them.")
    session = await _handed(service, tmp_path)
    await collect(service.send(session, "fix the tests"))
    await service.take_back_conversation("owner", session.thread_id)
    assert await service.conversation_agent("owner", session.thread_id) is None
    await collect(service.send(session, "what happened?"))
    _, *messages = script.requests[-1]
    header = " ".join(b["text"] for b in messages[-1].content if b.get("type") == "text")
    assert "handed this conversation to Claude Code" in header and f"Done in {tmp_path}" in messages[-2].content


async def test_an_agent_error_is_shown_and_nothing_is_added(service, tmp_path):
    session = await _handed(service, tmp_path)
    events = await collect(service.send(session, "break"))
    assert len(events) == 1 and isinstance(events[0], Error) and "the agent gave up" in events[0].message
    assert await service.conversation_messages(session.thread_id) == []


async def test_the_agent_gets_the_full_paths_of_the_files_sent_and_the_conversation_keeps_them(service, tmp_path):
    session = await _handed(service, tmp_path)
    photo = Attachment("photo.png", "image/png", b"\x89PNG")
    events = await collect(service.send(session, "look", [photo]))
    assert isinstance(events[-1], Done)
    message = asked()[0]["prompt"]
    assert message.startswith("look\n\nFiles sent with this message, saved on this computer:\n- ")
    saved = Path(message.splitlines()[-1].removeprefix("- ").removesuffix(" (photo.png)"))
    assert saved.read_bytes() == b"\x89PNG"
    assert [f.name for f in await service.list_files("owner")] == ["photo.png"]
    assert (await service.conversation_messages(session.thread_id))[0].text == "[attachment photo.png]\nlook"


async def test_only_an_installed_agent_and_an_existing_folder_can_be_handed_to(service, tmp_path):
    session = Session("owner", "cli", await service.new_thread("owner"))
    with pytest.raises(HandoffError, match="No plugin brings /codex"):
        await service.hand_conversation("owner", session.thread_id, "codex", str(tmp_path))
    with pytest.raises(HandoffError, match="isn't an existing folder"):
        await service.hand_conversation("owner", session.thread_id, "claude", str(tmp_path / "missing"))


async def test_a_restart_waits_until_the_agent_has_replied(service, tmp_path):
    """The agent may restart the daemon it answers through; stopping it at once would stop the agent."""
    session = await _handed(service, tmp_path)
    run = asyncio.create_task(collect(service.send(session, "work a while")))
    for _ in range(100):
        if asked():
            break
        await asyncio.sleep(0.02)
    stop = asyncio.Event()
    shutdown = Shutdown(service, stop, ByHand())
    assert shutdown.request(Ending.RESTART) == 1
    await asyncio.sleep(0.05)
    assert not stop.is_set()
    (tmp_path / "release").write_text("")
    assert isinstance((await run)[-1], Done)
    await asyncio.wait_for(stop.wait(), 1)
    assert shutdown.ending is Ending.RESTART


async def test_with_no_run_in_progress_a_restart_is_at_once(service):
    stop = asyncio.Event()
    shutdown = Shutdown(service, stop, ByHand())
    assert shutdown.request(Ending.RESTART) == 0
    await asyncio.wait_for(stop.wait(), 1)
    assert shutdown.ending is Ending.RESTART


async def test_the_workspace_is_created_when_handed_to_and_not_listed_as_recent(service):
    from assistant.core.config import settings

    session = Session("owner", "cli", await service.new_thread("owner"))
    workspace = str(Path(settings.agent_workspace_dir))
    handoff = await service.hand_conversation("owner", session.thread_id, "claude", workspace)
    assert handoff.folder == workspace and Path(workspace).is_dir()
    assert (await service.agent_folders("owner")).recent == []


async def test_folders_used_before_are_offered_newest_first_while_they_exist(service, tmp_path):
    first, second, gone = tmp_path / "first", tmp_path / "second", tmp_path / "gone"
    for folder in (first, second, gone):
        folder.mkdir()
    session = Session("owner", "cli", await service.new_thread("owner"))
    for folder in (first, gone, second, first):
        await service.hand_conversation("owner", session.thread_id, "claude", str(folder))
    gone.rmdir()
    assert (await service.agent_folders("owner")).recent == [str(first), str(second)]


async def test_browsing_lists_the_folders_inside_without_hidden_ones_or_files(service, tmp_path):
    root = tmp_path / "browsed"
    for name in ("b", "A", ".git"):
        (root / name).mkdir(parents=True)
    (root / "notes.txt").write_text("")
    listing = await service.child_folders(str(root))
    assert listing.children == [str(root / "A"), str(root / "b")]
    assert listing.parent == str(tmp_path)
    assert (await service.child_folders("/")).parent is None
    for wrong in ("relative", str(root / "missing"), str(root / "notes.txt")):
        with pytest.raises(FolderError):
            await service.child_folders(wrong)


async def test_each_message_continues_the_agents_session_in_that_folder(service, tmp_path):
    session = await _handed(service, tmp_path)
    first = await collect(service.send(session, "session"))
    second = await collect(service.send(session, "session"))
    assert first[0] == second[0] and first[0].text.startswith("Session ")
    assert asked()[1]["follow_up_of"] == asked()[0]["id"]


async def test_stopping_the_run_stops_the_agents_task(service, tmp_path):
    session = await _handed(service, tmp_path)
    run = asyncio.create_task(collect(service.send(session, "sleep")))
    for _ in range(200):
        task = asked()[0] if asked() else None
        if task and (folders.data("claude-code") / "tasks" / task["id"] / "pid").exists():
            break
        await asyncio.sleep(0.02)
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    found = await service.agent_tasks.state(asked()[0]["id"])
    assert found.state.status == "stopped"


async def test_a_plugin_written_for_the_old_agent_format_asks_to_be_updated(service, tmp_path):
    await service.store.aput(
        ("mcp_servers",),
        "old",
        {"name": "old", "command": "x", "agent_command": "codex", "agent_name": "Codex", "agent_tool": "converse"},
    )
    assert (await servers.load(service.store, "old")).agent_worker == ""
    session = Session("owner", "cli", await service.new_thread("owner"))
    with pytest.raises(HandoffError, match="Codex was written for an older version of lo9i"):
        await service.hand_conversation("owner", session.thread_id, "codex", str(tmp_path))


async def test_a_running_task_names_the_conversation_handed_to_the_agent(service, tmp_path):
    session = await _handed(service, tmp_path)
    run = asyncio.create_task(collect(service.send(session, "sleep")))
    async with asyncio.timeout(10):
        while not (running := await service.running_tasks()):
            await asyncio.sleep(0.02)
    assert [t.thread_id for t in running] == [session.thread_id]
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run


async def _working(service, session, tmp_path) -> str:
    """The agent's task in the conversation, once its worker has started."""
    async with asyncio.timeout(10):
        while True:
            task = await service.agent_tasks.working_in("claude-code", session.thread_id, str(tmp_path))
            if task and (folders.data("claude-code") / "tasks" / task / "pid").exists():
                return task
            await asyncio.sleep(0.02)


async def _taking_messages(service, session, tmp_path) -> str:
    task = await _working(service, session, tmp_path)
    async with asyncio.timeout(10):
        while not (folders.data("claude-code") / "tasks" / task / "inbox").is_dir():
            await asyncio.sleep(0.02)
    return task


async def test_messages_sent_while_the_agent_works_reach_it_and_show_among_its_steps(service, tmp_path):
    session = await _handed(service, tmp_path)
    run = asyncio.create_task(collect(service.send(session, "take messages")))
    await _taking_messages(service, session, tmp_path)
    await service.message_agent("owner", session.thread_id, "skip the slow tests")
    await service.interrupt_agent("owner", session.thread_id)
    await service.message_agent("owner", session.thread_id, "that's all")
    events = await run
    said = [e for e in events if isinstance(e, TextDelta | UserSaid)]
    assert said == [
        TextDelta("Working."),
        UserSaid("skip the slow tests"),
        UserSaid("that's all"),
        TextDelta("Took 3 messages."),  # its reply answers the last message
    ]
    assert ToolStarted("Interrupted", {}, within=events[2].id) in events and events[-1] == Done()
    shown = [(m.role, m.text) for m in await service.conversation_messages(session.thread_id)]
    assert shown[-6:] == [  # in order, after a reload
        ("user", "take messages"),
        ("assistant", "Working."),
        ("user", "skip the slow tests"),
        ("tool", "Interrupted"),
        ("user", "that's all"),
        ("assistant", "Took 3 messages."),
    ]


async def test_messages_the_agent_ended_without_taking_are_answered_next_in_its_session(service, tmp_path):
    session = await _handed(service, tmp_path)
    run = asyncio.create_task(collect(service.send(session, "take messages")))
    task = await _taking_messages(service, session, tmp_path)
    tasks = TaskStore(folders.data("claude-code") / "tasks")
    tasks.add_message(task, {"kind": "message", "text": "that's all"})
    tasks.add_message(task, {"kind": "message", "text": "and one more"})
    workers.wake(tasks.pid(task) or 0)
    events = await run
    assert [e for e in events if isinstance(e, UserSaid)] == [UserSaid("that's all"), UserSaid("and one more")]
    assert TextDelta(f"Done in {tmp_path}: and one more") in events and events[-1] == Done()
    assert (asked()[-1]["prompt"], asked()[-1]["follow_up_of"]) == ("and one more", task)


async def test_only_an_agent_at_work_that_takes_messages_gets_them(service, tmp_path):
    other = Session("owner", "cli", await service.new_thread("owner"))
    with pytest.raises(HandoffError, match="isn't handed to an agent"):
        await service.message_agent("owner", other.thread_id, "hello")
    session = await _handed(service, tmp_path)
    with pytest.raises(HandoffError, match="Claude Code isn't working on anything now"):
        await service.interrupt_agent("owner", session.thread_id)
    run = asyncio.create_task(collect(service.send(session, "work a while")))  # a worker without an inbox
    await _working(service, session, tmp_path)
    with pytest.raises(HandoffError, match="Claude Code can't take messages while it works"):
        await service.message_agent("owner", session.thread_id, "hello")
    (tmp_path / "release").write_text("")
    assert (await run)[-1] == Done()


async def test_the_list_of_running_tasks_hears_of_each_step_and_of_the_end(service, tmp_path):
    session = await _handed(service, tmp_path)
    after = service.bus.last_id
    await collect(service.send(session, "work out loud"))
    progress = [e.data for e in [e async for e in _events_after(service, after)] if e.kind == "agent_task_progress"]
    assert progress == [{"thread_id": session.thread_id}] * 7  # its 6 steps, then its end
    assert await service.running_tasks() == []


async def _events_after(service, after):
    """The bus events published since `after`."""
    async with asyncio.timeout(1):
        async for event in service.bus.subscribe(after):
            yield event
            if event.id == service.bus.last_id:
                return
