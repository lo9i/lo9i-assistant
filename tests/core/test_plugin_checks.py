"""A plugin's check of the values it was given (`check:` in its server.yaml, core/mcp/checks.py): a command or a tool
of its MCP server, run before the values are saved, whose error refuses them with its words. The checks really run."""

import sys

import pytest

from assistant.core.agent import McpServerChanges, ServerValues
from assistant.core.mcp import checks, folders, keys, servers
from assistant.core.mcp.checks import CheckFailedError
from assistant.core.mcp.servers import McpServer
from tests.core.test_repositories import URL, _write, repo  # noqa: F401 (a fixture)

_FIELDS = """
fields:
  - {key: GREET_TOKEN, label: Token, secret: true}
"""

# Says why on stdout, as a check does; the traceback-like line on stderr isn't shown.
_CHECK = """
import os, sys
if os.environ.get("GREET_TOKEN") != "good":
    print("The service refused the token.")
    sys.exit("Traceback: refused")
"""

_COMMAND = f"""
description: Greets
command: "{{python}}"
args: ["{{dir}}/server.py"]
check:
  command: "{{python}}"
  args: ["{{dir}}/check.py"]
{_FIELDS}"""

_SERVER = """
import os
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer("greet")


@server.tool()
def greet() -> str:
    \"\"\"Says hi.\"\"\"
    return "hi"


@server.tool()
def check_token() -> str:
    \"\"\"Whether the token works.\"\"\"
    if os.environ.get("GREET_TOKEN") != "good":
        raise ToolError("The service refused the token.")
    return "ok"


server.run()
"""

_TOOL = f"""
description: Greets
command: "{{python}}"
args: ["{{dir}}/server.py"]
check:
  tool: check_token
{_FIELDS}"""


def _plugin(root, manifest: str) -> None:
    files = {"server.yaml": manifest, "server.py": _SERVER, "check.py": _CHECK}
    _write(root / "other" / "general" / "greet", files)


async def _install(service, token: str, skills: list[str] | None = None):
    return await service.install_from_repository(URL, skills or [], [ServerValues("greet", {"GREET_TOKEN": token})])


async def test_a_check_command_refuses_values_that_dont_work_and_installs_nothing(service, repo):  # noqa: F811
    _plugin(repo, _COMMAND)
    found = next(s for s in (await service.browse_repository(URL)).servers if s.name == "greet")
    assert found.check
    with pytest.raises(CheckFailedError, match=r"^greet: The service refused the token\.$"):
        await _install(service, "bad", ["expenses"])
    # Nothing is saved, its code is taken out again, and the skill picked with it waits too.
    assert [s.name for s in await servers.load_all(service.store)] == []
    assert not folders.code("greet").exists()
    assert "expenses" not in {s.name for s in (await service.browse_repository(URL)).skills if s.installed}


async def test_values_the_check_takes_are_installed(service, repo):  # noqa: F811
    _plugin(repo, _COMMAND)
    installed = await _install(service, "good")
    assert [s.name for s in installed.servers] == ["greet"]
    server = await servers.load(service.store, "greet")
    assert server.check_args == [str(folders.code("greet") / "check.py")]


async def test_a_check_tool_refuses_values_and_is_never_the_agents(service, repo):  # noqa: F811
    _plugin(repo, _TOOL)
    with pytest.raises(CheckFailedError, match="The service refused the token"):
        await _install(service, "bad")
    assert await servers.load_all(service.store) == []
    await _install(service, "good")
    server = await servers.load(service.store, "greet")
    assert server.check_tool == "check_token"
    assert not server.selects("check_token") and server.selects("greet")


async def test_changing_a_plugins_env_runs_its_check_before_saving(service, repo):  # noqa: F811
    _plugin(repo, _COMMAND)
    await _install(service, "good")
    with pytest.raises(CheckFailedError, match="refused the token"):
        await service.update_mcp_server("greet", McpServerChanges(env={"GREET_TOKEN": "bad"}))
    kept = await keys.fill(service.store, service.secrets, await servers.load(service.store, "greet"))
    assert kept.env["GREET_TOKEN"] == "good"
    # Turning it off changes no value, so its check doesn't run.
    await service.update_mcp_server("greet", McpServerChanges(enabled=False))


async def test_a_field_left_empty_is_checked_with_its_saved_key(service, repo):  # noqa: F811
    _plugin(repo, _COMMAND)
    await _install(service, "good")
    await service.update_mcp_server("greet", McpServerChanges(env={"GREET_TOKEN": ""}))
    kept = await keys.fill(service.store, service.secrets, await servers.load(service.store, "greet"))
    assert kept.env["GREET_TOKEN"] == "good"


async def test_a_check_that_doesnt_end_in_time_fails(service, tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "CHECK_SECONDS", 0.5)
    sleeper = tmp_path / "sleep.py"
    sleeper.write_text("import time\ntime.sleep(30)\n")
    server = McpServer("slow", channel_command="x", check_command=sys.executable, check_args=[str(sleeper)])
    with pytest.raises(CheckFailedError, match=r"didn't finish within 0\.5s"):
        await service._plugin_checks.run(server)


def test_a_check_section_needs_a_command_or_a_tool():
    assert checks.parse(None) == {}
    assert checks.parse({"tool": "check"}) == {"check_command": "", "check_args": [], "check_tool": "check"}
    for wrong in ({}, {"command": "x", "tool": "y"}, "x", {"command": "x", "args": "y"}):
        with pytest.raises(ValueError, match="check"):
            checks.parse(wrong)
