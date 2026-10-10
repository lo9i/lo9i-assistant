"""Background work that ends after the call that started it returned: a coding agent's task, and work an MCP
server reports finished. Its end is told to the conversation that started it (a turn header note at the
user's next message there) and to the user (a notification in the apps, a message on the chat channel it
came from), unless the assistant read the end itself."""

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.store.memory import InMemoryStore

from assistant.core.agent import AssistantService, McpServer
from assistant.core.agent_tasks.reports import TaskReports
from assistant.core.background import Origin
from assistant.core.conversation import ended
from assistant.core.events import ApprovalRequired, ToolFinished
from assistant.core.mcp import folders
from assistant.core.mcp.on_demand import OnDemand
from tests.conftest import collect
from tests.core.test_handoffs import agent_plugin

_NOTE = "[Note for you, not from the user:]"
_SERVER = Path(__file__).with_name("fake_background_server.py")


class _Sender:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


@pytest.fixture
async def service(script, digests, summaries, titles) -> AsyncIterator[AssistantService]:
    """With the daemon's MCP hub and task ends running."""
    async with AssistantService.open() as svc:
        stop = asyncio.Event()
        running = [asyncio.create_task(svc.mcp.run(stop)), asyncio.create_task(svc.task_ends.run(stop))]
        yield svc
        stop.set()
        await asyncio.gather(*running)


async def _told(service: AssistantService, after: int) -> dict[str, Any]:
    """The next `background_ended` event after `after`."""
    async with asyncio.timeout(30):
        async for event in service.bus.subscribe(after):
            if event.kind == "background_ended":
                return event.data
    raise AssertionError("the bus stopped")


def _notes(request: list[BaseMessage]) -> str:
    """The notes in the turn header of the request's last user message."""
    message = next(m for m in reversed(request) if isinstance(m, HumanMessage))
    blocks = message.content if isinstance(message.content, list) else []
    return "\n".join(b["text"] for b in blocks if isinstance(b, dict) and b.get("text", "").startswith(_NOTE))


async def _until(condition) -> None:
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("never happened")


async def _start_task(service: AssistantService, script, session, folder: Path, task: str) -> str:
    """Started in the background: in home, kept there."""
    script.call("start_task", agent="claude-code", repository=str(folder), task=task).reply("Started it.")
    events = await collect(service.send(session, "hand it to claude"))
    asked = next(e for e in events if isinstance(e, ApprovalRequired))
    events = await collect(service.resume(session, {asked.interrupt_id: {"moved": False}}))
    return next(e for e in events if isinstance(e, ToolFinished)).output.split()[2]


async def test_a_tasks_end_is_told_on_its_channel_and_once_in_the_next_turn_header(service, script, tmp_path):
    await service.add_mcp_server(agent_plugin(trusted=True))
    sender = _Sender()
    service.outbox.register("telegram", sender)
    session = await service.session("owner", "telegram")
    after = service.bus.last_id
    task_id = await _start_task(service, script, session, tmp_path, "finish")
    told = await _told(service, after)
    assert told["ok"] and told["thread_id"] == session.thread_id and told["channel"] == "telegram"
    assert told["text"] == f"✅ Claude Code finished task {task_id} (finish): Done in {tmp_path}: finish"
    await _until(lambda: sender.sent == [told["text"]])
    await collect(service.send(session, "how did it go?"))
    note = _notes(script.requests[-1])
    assert f'Claude Code\'s task {task_id} in {tmp_path}, asked "finish", is done: Done in' in note
    assert "[You sent this on" not in str(script.requests[-1][-1].content)  # it's this channel's conversation
    await collect(service.send(session, "and now?"))
    assert _notes(script.requests[-1]) == ""


async def test_a_failed_task_is_told_as_a_warning(service, script, tmp_path):
    await service.add_mcp_server(agent_plugin(trusted=True))
    after = service.bus.last_id
    task_id = await _start_task(service, script, await service.session("owner", "web"), tmp_path, "break")
    told = await _told(service, after)
    assert not told["ok"] and told["text"] == f"⚠️ Claude Code's task {task_id} (break) failed: the agent gave up"


async def test_a_task_whose_end_the_assistant_read_isnt_told(script, digests, summaries, titles, tmp_path):
    async with AssistantService.open() as service:
        await service.add_mcp_server(agent_plugin(trusted=True))
        session = await service.session("owner", "web")
        task_id = await _start_task(service, script, session, tmp_path, "finish")
        reports = TaskReports(service.store)
        assert await reports.expected() == [task_id]
        script.call("task_status", task_id=task_id, wait_seconds=30).reply("It's done.")
        events = await collect(service.send(session, "is it done?"))
        assert "Result:" in next(e for e in events if isinstance(e, ToolFinished)).output
        assert await reports.expected() == []


async def test_an_end_waits_while_the_assistant_reads_the_task_and_isnt_told_once_seen():
    store = InMemoryStore()
    reports, origin = TaskReports(store), Origin("owner", "t1", "web")
    await reports.expect("a1", origin)
    await ended.record(store, "owner", "t1", "task:a1", "a1 is done")
    told: list[Origin | None] = []

    async def tell() -> None:
        async with reports.ending("a1") as to:
            told.append(to)

    async with reports.reading("a1"):
        telling = asyncio.create_task(tell())
        await asyncio.sleep(0.05)
        assert told == []
        await reports.seen("a1", origin)
    await telling
    assert told == [None] and await ended.take(store, "owner", "t1") == []
    await reports.expect("b2", origin)
    async with reports.ending("b2") as to:
        assert to == origin
    assert await reports.expected() == []


async def test_an_mcp_servers_background_work_is_told_to_the_conversation_that_started_it(service, script):
    await service.add_mcp_server(McpServer(name="convert", command=sys.executable, args=[str(_SERVER)], trusted=True))
    await _until(lambda: service.mcp.state("convert")[0] == "connected")
    session = await service.session("owner", "cli")
    after = service.bus.last_id
    script.call("mcp__convert__start_work", name="photos").reply("Working on it.")
    await collect(service.send(session, "convert my photos"))
    told = await _told(service, after)
    assert told == {
        "thread_id": session.thread_id,
        "channel": "cli",
        "ok": True,
        "text": "✅ convert: photos is ready: 3 files converted.",
    }
    await collect(service.send(session, "done?"))
    assert "The MCP server convert says its background work photos finished: photos is ready" in _notes(
        script.requests[-1]
    )


async def test_a_server_on_demand_isnt_idle_while_its_background_work_is_in_progress():
    async def save(tools) -> None:
        pass

    on_demand = OnDemand([], save, idle_seconds=0.05)
    on_demand.started_work("photos")
    idle = asyncio.create_task(on_demand.idle())
    await asyncio.sleep(0.2)
    assert not idle.done()
    on_demand.finished_work("photos")
    await asyncio.wait_for(idle, 5)
    assert not on_demand.wanted


async def test_a_running_task_is_listed_with_its_conversation_and_each_step_is_an_event(service, script, tmp_path):
    await service.add_mcp_server(agent_plugin(trusted=True))
    session = await service.session("owner", "web")
    task_id = await _start_task(service, script, session, tmp_path, "work a while")
    [running] = await service.running_tasks()
    assert (running.id, running.agent, running.thread_id) == (task_id, "Claude Code", session.thread_id)
    assert running.asked == "work a while" and running.steps == []
    after = service.bus.last_id
    with (folders.data("claude-code") / "tasks" / task_id / "progress.log").open("a") as log:
        log.write('{"kind": "tool", "tool": "Bash", "detail": "pytest"}\n')
    async with asyncio.timeout(30):
        async for event in service.bus.subscribe(after):
            if event.kind == "agent_task_progress":
                assert event.data == {"task_id": task_id}
                break
    assert (await service.running_tasks())[0].steps == ["Bash: pytest"]
    (tmp_path / "release").touch()
    await service.agent_tasks.ended(task_id)
    assert await service.running_tasks() == []
