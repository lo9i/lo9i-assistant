"""Coding tasks beside the conversation that started them: start_task runs the task in the background and the
conversation stays the assistant's; the web app shows each agent session in a panel beside it, step by step, and the
user writes to the agent there: between its steps while it works and takes messages, else as the next task of the same
session. The assistant's task's end comes back to the conversation, which the assistant follows up."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from lo9i.core.agent import AssistantService, Session
from lo9i.core.agent_tasks.beside import SessionNotFoundError, TasksBesideError, TaskStep
from lo9i.core.conversation import queued
from lo9i.core.events import ToolFinished
from lo9i.core.mcp import folders
from tests.conftest import collect
from tests.core.test_handoffs import agent_plugin, asked

_NOTE = "[Note for you, not from the user:]"


@pytest.fixture
async def service(script, digests, summaries, titles) -> AsyncIterator[AssistantService]:
    """With an agent plugin, and the daemon's following of tasks beside conversations and of their ends running."""
    async with AssistantService.open() as svc:
        await svc.add_mcp_server(agent_plugin(trusted=True))
        stop = asyncio.Event()
        running = [asyncio.create_task(svc.tasks_beside.run(stop)), asyncio.create_task(svc.task_ends.run(stop))]
        yield svc
        stop.set()
        await asyncio.gather(*running)


async def _started(service: AssistantService, script, folder: Path, task: str, title: str = "") -> Session:
    """A conversation where the assistant started `task` with start_task."""
    session = Session("owner", "web", await service.new_thread("owner"))
    args = {"title": title} if title else {}
    script.call("start_task", agent="claude-code", repository=str(folder), task=task, **args).reply("It's on it.")
    await collect(service.send(session, "fix the tests with claude"))
    return session


async def _until(condition) -> Any:
    for _ in range(1000):
        if found := await condition():
            return found
        await asyncio.sleep(0.01)
    raise TimeoutError("never happened")


async def _session_id(service: AssistantService, session: Session) -> str:
    [listed] = await service.task_sessions("owner", session.thread_id)
    return listed.id


async def _status(service: AssistantService, session: Session, status: str) -> bool:
    return [s.status for s in await service.task_sessions("owner", session.thread_id)] == [status]


async def test_a_task_started_in_a_conversation_runs_beside_it_and_the_conversation_stays_the_assistants(
    service, script, tmp_path
):
    session = Session("owner", "web", await service.new_thread("owner"))
    script.call("start_task", agent="claude-code", repository=str(tmp_path), task="work a while", title="Fix tests")
    script.reply("Claude is on it; ask me anything meanwhile.")
    events = await collect(service.send(session, "fix the tests with claude"))
    started = next(e for e in events if isinstance(e, ToolFinished)).output
    assert started.startswith("Started task ") and "panel beside this conversation" in started
    assert await service.conversation_agent("owner", session.thread_id) is None
    assert await service.queued_threads("owner") == []
    [listed] = await service.task_sessions("owner", session.thread_id)
    assert (listed.name, listed.title, listed.repository, listed.status) == (
        "Claude Code",
        "Fix tests",
        str(tmp_path),
        "running",
    )
    # The user goes on talking to the assistant while it works, and the assistant knows how it's going.
    script.reply("It's still running the tests.")
    await collect(service.send(session, "how is it going?"))
    note = next(b["text"] for b in script.requests[-1][-1].content if b.get("text", "").startswith(_NOTE))
    assert 'Claude Code, "Fix tests" in' in note and "task_status reads one's steps" in note
    (tmp_path / "release").touch()
    await _until(lambda: _status(service, session, "done"))


async def test_its_steps_show_beside_the_conversation_as_they_come(service, script, tmp_path):
    session = await _started(service, script, tmp_path, "work a while")
    session_id = await _session_id(service, session)
    [running] = await service.running_tasks()
    assert running.thread_id == session.thread_id
    after = service.bus.last_id
    with (folders.data("claude-code") / "tasks" / running.id / "progress.log").open("a") as log:
        log.write('{"kind": "text_delta", "text": "Run"}\n')
        log.write('{"kind": "tool", "tool": "Bash", "detail": "pytest", "id": "t1"}\n')
    step = await _next_step(service, after)
    assert step == {
        "thread_id": session.thread_id,
        "session_id": session_id,
        "task_id": running.id,
        "index": 0,  # its place among the task's steps, not counting the words streamed
        "step": {
            "kind": "tool",
            "text": "",
            "tool": "Bash",
            "detail": "pytest",
            "id": "t1",
            "within": "",
            "waiting": False,
        },
    }
    details = await service.task_session("owner", session.thread_id, session_id)
    [turn] = details.turns
    assert (turn.asked, turn.from_user, turn.status) == ("work a while", False, "running")
    assert turn.steps == [TaskStep("tool", tool="Bash", detail="pytest", id="t1")]  # not the words streamed
    (tmp_path / "release").touch()
    await _until(lambda: _status(service, session, "done"))
    [turn] = (await service.task_session("owner", session.thread_id, session_id)).turns
    assert turn.result == f"Done in {tmp_path}: work a while" and turn.finished_at


async def test_the_assistants_task_ends_in_the_conversation_and_the_assistant_follows_it_up(service, script, tmp_path):
    session = await _started(service, script, tmp_path, "finish")
    waiting = await _until(lambda: queued.first(service.store, "owner", session.thread_id))
    assert waiting.follow_up and waiting.text.startswith("✅ Claude Code finished task ")
    script.reply("Claude fixed the tests.")
    await collect(service.follow_up(session, waiting.text))
    shown = [(m.role, m.text) for m in await service.conversation_messages(session.thread_id)][-2:]
    assert shown == [("notice", waiting.text), ("assistant", "Claude fixed the tests.")]


async def test_written_while_it_works_the_agent_gets_it_between_its_steps(service, script, tmp_path):
    session = await _started(service, script, tmp_path, "take messages")
    session_id = await _session_id(service, session)
    await _until(lambda: _turns(service, session, session_id, 1, "running", steps=1))
    assert await service.message_task_session("owner", session.thread_id, session_id, "use the fixtures") == "taken"
    assert await service.message_task_session("owner", session.thread_id, session_id, "that's all") == "taken"
    await _until(lambda: _status(service, session, "done"))
    [turn] = (await service.task_session("owner", session.thread_id, session_id)).turns
    assert [(s.kind, s.text) for s in turn.steps if s.kind == "user"] == [
        ("user", "use the fixtures"),
        ("user", "that's all"),
    ]
    assert len(asked()) == 1


async def test_a_message_its_worker_hasnt_passed_on_yet_shows_waiting(service, script, tmp_path):
    session = await _started(service, script, tmp_path, "hold messages")
    session_id = await _session_id(service, session)
    await _until(lambda: _turns(service, session, session_id, 1, "running", steps=1))
    after = service.bus.last_id
    assert await service.message_task_session("owner", session.thread_id, session_id, "unread yet") == "taken"
    [turn] = (await service.task_session("owner", session.thread_id, session_id)).turns
    [unread] = turn.unread
    assert (unread.kind, unread.text, unread.waiting) == ("user", "unread yet", True)
    async with asyncio.timeout(10):  # the apps load it again
        async for event in service.bus.subscribe(after):
            if event.kind == "tasks_beside" and event.data.get("session_id") == session_id:
                break
    await service.stop_task_session("owner", session.thread_id, session_id)


async def test_an_agent_that_cant_take_messages_gets_it_as_the_next_task_of_its_session(service, script, tmp_path):
    session = await _started(service, script, tmp_path, "work a while")
    session_id = await _session_id(service, session)
    assert await service.message_task_session("owner", session.thread_id, session_id, "and the docs") == "later"
    assert (await service.task_sessions("owner", session.thread_id))[0].waiting == 1
    (tmp_path / "release").touch()
    details = await _until(lambda: _turns(service, session, session_id, 2, "done"))
    first, then = details.turns
    assert (then.asked, then.from_user) == ("and the docs", True)
    assert [t["follow_up_of"] for t in asked()] == ["", first.id]
    assert asked()[0]["session"] == asked()[1]["session"] == session_id
    assert details.waiting == []


async def test_written_after_it_ended_it_starts_the_next_task_at_once(service, script, tmp_path):
    session = await _started(service, script, tmp_path, "finish")
    session_id = await _session_id(service, session)
    await _until(lambda: _status(service, session, "done"))
    assert await service.message_task_session("owner", session.thread_id, session_id, "now the docs") == "started"
    details = await _until(lambda: _turns(service, session, session_id, 2, "done"))
    assert details.turns[1].result == f"Done in {tmp_path}: now the docs"


async def test_what_the_agent_ended_without_taking_goes_on_as_its_next_task(service, script, tmp_path):
    session = await _started(service, script, tmp_path, "leave messages")
    session_id = await _session_id(service, session)
    await _until(lambda: _turns(service, session, session_id, 1, "running", steps=1))
    assert await service.message_task_session("owner", session.thread_id, session_id, "and the docs") == "taken"
    (tmp_path / "release").touch()
    details = await _until(lambda: _turns(service, session, session_id, 2, "done"))
    assert details.turns[1].asked == "and the docs"


async def test_a_task_the_user_started_beside_the_conversation_isnt_told_there(service, script, tmp_path):
    session = await _started(service, script, tmp_path, "finish")
    session_id = await _session_id(service, session)
    await _until(lambda: queued.first(service.store, "owner", session.thread_id))
    await queued.take(service.store, "owner", session.thread_id)
    await service.message_task_session("owner", session.thread_id, session_id, "now the docs")
    await _until(lambda: _turns(service, session, session_id, 2, "done"))
    await asyncio.sleep(0.3)
    assert await queued.first(service.store, "owner", session.thread_id) is None


async def test_stopped_from_beside_the_conversation_its_end_isnt_told_and_then_it_can_be_removed(
    service, script, tmp_path
):
    session = await _started(service, script, tmp_path, "sleep")
    session_id = await _session_id(service, session)
    with pytest.raises(TasksBesideError):
        await service.remove_task_session("owner", session.thread_id, session_id)
    stopped = await service.stop_task_session("owner", session.thread_id, session_id)
    assert stopped.status == "stopped"
    with pytest.raises(TasksBesideError):
        await service.stop_task_session("owner", session.thread_id, session_id)
    await asyncio.sleep(0.3)
    assert await queued.first(service.store, "owner", session.thread_id) is None
    await service.remove_task_session("owner", session.thread_id, session_id)
    assert await service.task_sessions("owner", session.thread_id) == []
    with pytest.raises(SessionNotFoundError):
        await service.task_session("owner", session.thread_id, session_id)


async def test_a_deleted_conversation_forgets_its_tasks(service, script, tmp_path):
    session = await _started(service, script, tmp_path, "finish")
    await _until(lambda: _status(service, session, "done"))
    await service.delete_conversation("owner", session.thread_id)
    assert await service.task_sessions("owner", session.thread_id) == []


async def test_written_before_its_worker_takes_messages_it_gets_it_once_it_does(service, script, tmp_path):
    session = await _started(service, script, tmp_path, "take messages once released")
    session_id = await _session_id(service, session)
    assert await service.message_task_session("owner", session.thread_id, session_id, "that's all") == "later"
    (tmp_path / "release").touch()
    details = await _until(lambda: _turns(service, session, session_id, 1, "done"))
    assert [(s.kind, s.text) for s in details.turns[0].steps] == [("text", "Working."), ("user", "that's all")]
    assert len(asked()) == 1


async def _next_step(service: AssistantService, after: int) -> dict[str, Any]:
    async with asyncio.timeout(30):
        async for event in service.bus.subscribe(after):
            if event.kind == "agent_task_step":
                return event.data
    raise AssertionError("the bus stopped")


async def _turns(service: AssistantService, session: Session, session_id: str, count: int, status: str, steps: int = 0):
    """The session's details once it has `count` tasks, the last one `status` with at least `steps` steps."""
    details = await service.task_session("owner", session.thread_id, session_id)
    last = details.turns[-1]
    return details if len(details.turns) == count and last.status == status and len(last.steps) >= steps else None
