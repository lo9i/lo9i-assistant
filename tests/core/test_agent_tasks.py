"""Coding tasks handed to an installed agent: the task tools come with the agent plugin, starting a task
asks the user unless the plugin is trusted, and a task is followed to its result."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from assistant.core.agent import AssistantService
from assistant.core.agent_tasks.service import AgentTaskError
from assistant.core.events import ApprovalRequired, ToolFinished
from assistant.core.mcp import folders
from tests.conftest import collect
from tests.core.test_handoffs import agent_plugin

_TOOLS = ["list_tasks", "start_task", "stop_task", "task_status"]


@pytest.fixture
async def service(script, digests, summaries, titles) -> AsyncIterator[AssistantService]:
    async with AssistantService.open() as svc:
        yield svc


def _offered(service: AssistantService) -> list[str]:
    return [d["function"]["name"] for d in service._plugin_tools.definitions()]


async def test_the_task_tools_come_with_an_agent_plugin_and_name_its_agents(service):
    assert _offered(service) == []
    await service.add_mcp_server(agent_plugin())
    assert _offered(service) == _TOOLS
    start = next(d for d in service._plugin_tools.definitions() if d["function"]["name"] == "start_task")
    assert start["function"]["description"].endswith("Agents: claude-code (Claude Code).")
    assert service._plugin_tools.read_only_definitions() == []  # subagents don't start tasks
    await service.remove_mcp_server("claude-code")
    assert _offered(service) == [] and "no coding agent plugin" in service._plugin_tools.unavailable("start_task")


async def test_starting_a_task_asks_first_and_the_task_is_followed_to_its_result(service, script, tmp_path):
    await service.add_mcp_server(agent_plugin())
    script.call("start_task", agent="claude-code", repository=str(tmp_path), task="finish").reply("Started it.")
    session = await service.session("owner", "cli")
    events = await collect(service.send(session, "fix the tests with claude"))
    asked = next(e for e in events if isinstance(e, ApprovalRequired))
    assert asked.request["tool"] == "claude-code" and "finish" in asked.request["command"]
    events = await collect(service.resume(session, {asked.interrupt_id: {"approved": True, "reason": ""}}))
    started = next(e for e in events if isinstance(e, ToolFinished))
    assert started.output.startswith("Started task ")
    task_id = started.output.split()[2]
    found = await service.agent_tasks.wait(task_id, 30)
    assert found.state.status == "done" and found.state.outcome.text == f"Done in {tmp_path}: finish"
    assert [f.state.task.id for f in await service.agent_tasks.recent()] == [task_id]


async def test_a_trusted_agent_starts_tasks_without_asking(service, script, tmp_path):
    await service.add_mcp_server(agent_plugin(trusted=True))
    script.call("start_task", agent="claude-code", repository=str(tmp_path), task="finish").reply("ok")
    events = await collect(service.send(await service.session("owner", "cli"), "go"))
    assert not any(isinstance(e, ApprovalRequired) for e in events)
    assert next(e for e in events if isinstance(e, ToolFinished)).output.startswith("Started task ")


async def test_status_shows_steps_and_stop_stops_a_running_task(service, tmp_path):
    await service.add_mcp_server(agent_plugin(trusted=True))
    tasks = service.agent_tasks
    done = await tasks.start("claude-code", str(tmp_path), "show your steps")
    await tasks.wait(done.id, 30)
    tools = {t: service._plugin_tools.tool(t) for t in _TOOLS}
    status = await tools["task_status"].ainvoke({"task_id": done.id})
    assert "Latest steps:\n- Read: README.md\n- Ran: pytest" in status and "Result:" in status
    running = await tasks.start("claude-code", str(tmp_path), "sleep")
    pid = folders.data("claude-code") / "tasks" / running.id / "pid"
    for _ in range(200):
        if pid.exists():
            break
        await asyncio.sleep(0.02)
    assert (await tasks.stop(running.id)).state.status == "stopped"
    assert "isn't running" in await tools["stop_task"].ainvoke({"task_id": running.id})
    listed = await tools["list_tasks"].ainvoke({})
    assert listed.index(running.id) < listed.index(done.id) and "(Claude Code)" in listed


async def test_unknown_agents_folders_and_tasks_are_said_so(service, tmp_path):
    await service.add_mcp_server(agent_plugin(trusted=True))
    with pytest.raises(AgentTaskError, match="No coding agent 'codex'"):
        await service.agent_tasks.start("codex", str(tmp_path), "finish")
    with pytest.raises(AgentTaskError, match="isn't an existing folder"):
        await service.agent_tasks.start("claude-code", "relative", "finish")
    assert "No task nope" in await service._plugin_tools.tool("task_status").ainvoke({"task_id": "nope"})


def test_an_agents_worker_needs_format_3_and_libraries_arent_installed(tmp_path):
    from assistant.core.mcp import install
    from assistant.core.repositories.errors import RepositoryError

    folder = tmp_path / "assistant" / "agents" / "claude-code"
    folder.mkdir(parents=True)
    agent = "agent: {command: claude, name: Claude Code, worker: '{bin}/claude-code-worker'}\n"
    for yaml_text, problem in (
        (f"format: 2\n{agent}", "needs format: 3"),
        (f"format: 3\nlibraries: [agent-tasks]\n{agent}", "libraries"),
    ):
        (folder / "server.yaml").write_text(yaml_text)
        with pytest.raises(RepositoryError, match=problem):
            install._candidate(tmp_path, folder, "claude-code")
    (folder / "server.yaml").write_text(f"format: 3\n{agent}")
    found = install._candidate(tmp_path, folder, "claude-code")
    assert found is not None and found.template.agent_worker == "{bin}/claude-code-worker"
