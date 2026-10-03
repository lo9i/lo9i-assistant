"""Failures of MCP servers and skills: counted in a row, cleared by a success, alerted once at
FAILING_AFTER, and shown with the server or skill. Skills are also checked as written."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from mcp import Client
from mcp.server import MCPServer

from assistant.core.agent import AssistantService, McpServer, McpServerChanges
from assistant.core.health import FAILING_AFTER
from assistant.core.mcp import hub as hub_module
from assistant.core.skills import store
from assistant.core.skills.errors import SkillError
from tests.conftest import collect


@pytest.fixture
def skills_dir(isolated_settings, monkeypatch):
    monkeypatch.setattr("assistant.core.config.settings.skills_dir", str(isolated_settings / "skills"))
    return isolated_settings / "skills"


@pytest.fixture
def alerts(service, monkeypatch) -> list[dict[str, Any]]:
    """The `failing` events the service publishes."""
    seen: list[dict[str, Any]] = []
    publish = service.bus.publish

    def record(kind: str, **data: Any) -> None:
        if kind == "failing":
            seen.append(data)
        publish(kind, **data)

    monkeypatch.setattr(service.bus, "publish", record)
    return seen


def _disk_server() -> MCPServer:
    server = MCPServer("disk")

    @server.tool()
    def write(text: str) -> str:
        """Write text."""
        if text == "fail":
            raise ValueError("disk full")
        return "written"

    return server


@pytest.fixture
async def service(script, digests, titles, monkeypatch) -> AsyncIterator[AssistantService]:
    fake = _disk_server()
    monkeypatch.setattr(hub_module, "open_client", lambda server, handler: Client(fake, message_handler=handler))
    async with AssistantService.open() as svc:
        stop = asyncio.Event()
        task = asyncio.create_task(svc.mcp.run(stop))
        yield svc
        stop.set()
        await task


async def _connect(service: AssistantService) -> None:
    await service.add_mcp_server(McpServer(name="disk", command="disk-server", trusted=True))
    for _ in range(100):
        if (await service.mcp_servers())[0].status == "connected":
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("the server never connected")


async def _say(service: AssistantService, text: str) -> list:
    return await collect(service.send(await service.session("owner", "cli"), text))


async def test_mcp_failures_in_a_row_alert_once_and_a_success_clears_them(service, script, alerts):
    await _connect(service)
    await _say(service, "hi")
    for _ in range(FAILING_AFTER + 1):
        script.call("mcp__disk__write", text="fail")
    await _say(service, "write")
    [status] = await service.mcp_servers()
    assert (
        status.failing
        and status.failures == FAILING_AFTER + 1
        and status.failure == "write: Error executing tool write"
        and status.failed_at
    )
    assert alerts == [{"area": "mcp", "name": "disk", "error": status.failure}]
    script.call("mcp__disk__write", text="hello")
    await _say(service, "write")
    [status] = await service.mcp_servers()
    assert status.failures == 0 and status.failure == "write: Error executing tool write"


async def test_a_server_that_cant_connect_counts_a_failure(service, monkeypatch):
    def refuse(server, handler):
        raise OSError("no such command")

    monkeypatch.setattr(service.mcp, "_factory", refuse)
    await service.add_mcp_server(McpServer(name="disk", command="disk-server"))
    [status] = await service.mcp_servers()
    for _ in range(100):
        if status.failures:
            break
        await asyncio.sleep(0.02)
        [status] = await service.mcp_servers()
    assert status.status == "failed" and status.failure == "Couldn't connect: no such command"


async def test_removing_a_server_forgets_its_failures(service, script):
    await _connect(service)
    await _say(service, "hi")
    script.call("mcp__disk__write", text="fail")
    await _say(service, "write")
    await service.remove_mcp_server("disk")
    assert (await service.mcp.health("disk")).failures == 0


async def test_failing_skill_scripts_count_for_their_skill(service, script, skills_dir, alerts):
    store.save("backup", "Back up files", "Run scripts/run.sh", {"scripts/run.sh": "exit 1"})
    command = f"bash {skills_dir / 'backup' / 'scripts' / 'run.sh'}"
    for _ in range(FAILING_AFTER):
        script.call("bash", command=command)
    await _say(service, "back up")
    [skill] = await service.list_skills()
    assert skill.failures == FAILING_AFTER and skill.failure.startswith("exit code: 1")
    assert alerts == [{"area": "skill", "name": "backup", "error": skill.failure}]
    store.save("backup", "Back up files", "Run scripts/run.sh", {"scripts/run.sh": "exit 0"})
    script.call("bash", command=command)
    await _say(service, "again")
    assert (await service.list_skills())[0].failures == 0


async def test_commands_outside_skill_folders_count_for_no_skill(service, script, skills_dir):
    store.save("backup", "Back up files", "Run it")
    script.call("bash", command="exit 1")
    await _say(service, "fail")
    assert (await service.list_skills())[0].failures == 0


def test_a_broken_header_is_listed_as_a_problem_instead_of_breaking_the_list(skills_dir):
    (skills_dir / "broken").mkdir(parents=True)
    (skills_dir / "broken" / "SKILL.md").write_text("---\nname: [broken\n---\n\nSteps.")
    [skill] = store.saved_skills()
    assert skill.name == "broken" and skill.problems[0].startswith("The header of its SKILL.md isn't valid YAML")


def test_instructions_that_use_missing_files_are_a_problem(skills_dir):
    (skills_dir / "report").mkdir(parents=True)
    (skills_dir / "report" / "SKILL.md").write_text("Run scripts/report.py, then read references/.")
    assert store.load("report").problems == ["Its instructions use files it doesn't have: scripts/report.py."]
    with pytest.raises(SkillError, match=r"scripts/report\.py"):
        store.save("report", "Reports", "Run scripts/report.py.")


async def test_use_skill_tells_the_model_about_problems(service, script, skills_dir):
    (skills_dir / "report").mkdir(parents=True)
    (skills_dir / "report" / "SKILL.md").write_text("---\nname: report\ndescription: Reports\n---\n\nRun scripts/a.py")
    script.call("use_skill", name="report").reply("done")
    [finished] = [e for e in await _say(service, "report") if hasattr(e, "output")]
    assert "This skill has problems" in finished.output and "scripts/a.py" in finished.output


async def test_save_skill_refuses_missing_files_before_asking(service, script, skills_dir):
    script.call("save_skill", name="report", description="Reports", instructions="Run scripts/a.py").reply("ok")
    [finished] = [e for e in await _say(service, "save") if hasattr(e, "output")]
    assert finished.output == "Its instructions use files it doesn't have: scripts/a.py."
    assert not (skills_dir / "report").exists()


async def _fail_server(service: AssistantService, script, times: int = FAILING_AFTER) -> None:
    for _ in range(times):
        script.call("mcp__disk__write", text="fail")
    await _say(service, "write")


async def test_failing_servers_and_skills_are_alerts_until_dismissed(service, script, skills_dir):
    await _connect(service)
    await _say(service, "hi")
    await _fail_server(service, script, FAILING_AFTER - 1)
    assert await service.alerts() == []
    await _fail_server(service, script, 1)
    [alert] = await service.alerts()
    assert (alert.area, alert.name, alert.failures) == ("mcp", "disk", FAILING_AFTER)
    await service.dismiss_alert("mcp", "disk")
    await _fail_server(service, script, 1)
    assert await service.alerts() == []


async def test_a_dismissed_alert_comes_back_after_it_works_and_fails_again(service, script):
    await _connect(service)
    await _say(service, "hi")
    await _fail_server(service, script)
    await service.dismiss_alert("mcp", "disk")
    script.call("mcp__disk__write", text="hello")
    await _say(service, "write")
    await _fail_server(service, script)
    assert [a.name for a in await service.alerts()] == ["disk"]


async def test_turned_off_servers_and_deleted_skills_have_no_alerts(service, script, skills_dir):
    await _connect(service)
    await _say(service, "hi")
    await _fail_server(service, script)
    store.save("backup", "Back up files", "Run scripts/run.sh", {"scripts/run.sh": "exit 1"})
    for _ in range(FAILING_AFTER):
        script.call("bash", command=f"bash {skills_dir / 'backup' / 'scripts' / 'run.sh'}")
    await _say(service, "back up")
    assert {a.name for a in await service.alerts()} == {"disk", "backup"}
    await service.update_mcp_server("disk", McpServerChanges(enabled=False))
    await service.delete_skill("backup")
    assert await service.alerts() == []
