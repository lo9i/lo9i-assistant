"""Installing skills and MCP servers from a git repository. The download is replaced by a copy of a
local folder; installed local servers really run."""

import asyncio
import re
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from assistant.core.agent import (
    McpServer,
    McpServerChanges,
    McpServerError,
    RepositoryError,
    ServerValues,
    SkillError,
)
from assistant.core.mcp import install, keys, servers
from assistant.core.repositories import check, checkout
from assistant.core.repositories.icons import PluginIcon
from assistant.core.repositories.source import Source
from assistant.core.skills import install as skill_install
from assistant.core.skills import store
from assistant.core.uv import find as find_uv
from tests.core.test_plugin_icons import BRAND

URL = "https://example.com/me/lo9i-extras.git"

_SERVER = """
import os
from mcp.server import MCPServer

server = MCPServer("hello")


@server.tool()
def whoami() -> str:
    \"\"\"Who the user is.\"\"\"
    return os.environ["HELLO_USER"]


server.run()
"""

_MANIFEST = """
name: hello
description: Says who you are
command: "{python}"
args: ["{dir}/server.py"]
env: {HELLO_GREETING: hi}
fields:
  - {key: HELLO_USER, label: Your name}
  - {key: HELLO_TOKEN, label: Token, secret: true, help: https://example.com/token}
"""


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    """Two skills, a local and a remote server, in the other folder, the way the download sees them."""
    root = tmp_path / "remote"
    _skill(root / "other" / "general" / "expenses", "expenses", "Track expenses", {"scripts/add.py": "print('v1')"})
    _skill(root / "other" / "general" / "news", "news-digest", "Daily news", {})
    _write(root / "other" / "general" / "hello", {"server.yaml": _MANIFEST, "server.py": _SERVER})
    _write(
        root / "other" / "general" / "tasks",
        {"server.yaml": "url: https://tasks.example.com/mcp\nfields: [{key: Authorization, label: Token}]"},
    )
    _write(root / ".git", {"config": "[core]"})
    (root / "other" / "general" / "expenses" / "link.py").symlink_to("/etc/hosts")

    async def fetch(url: str, dest: Path, token: str = "") -> str:
        REMOTE["downloads"] += 1
        shutil.copytree(root, dest, symlinks=True)
        return REMOTE["head"] or "head1"

    async def latest_commit(url: str, token: str = "") -> str:
        if REMOTE["head"] is None:
            raise RepositoryError("Couldn't get the repository: no network")
        return REMOTE["head"]

    REMOTE.update(head="head1", downloads=0)
    monkeypatch.setattr(checkout, "_fetch", fetch)
    monkeypatch.setattr(checkout, "latest_commit", latest_commit)
    return root


# The remote's latest commit (None: unreachable) and how often it was downloaded.
REMOTE: dict = {}


def _skill(folder: Path, name: str | None, description: str, files: dict[str, str]) -> None:
    header = f"---\nname: {name}\ndescription: {description}\n---\n\n" if name else ""
    _write(folder, {"SKILL.md": f"{header}Steps for {description}.", **files})


def _write(folder: Path, files: dict[str, str]) -> None:
    for path, content in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text(content)


HELLO = ServerValues("hello", {"HELLO_USER": "Ana", "HELLO_TOKEN": "s3cret"})


async def _problems(service) -> str:
    """What the listing says about the plugins it left out."""
    return " ".join((await service.browse_repository(URL)).problems)


async def test_browse_lists_skills_and_servers(service, repo, isolated_settings):
    contents = await service.browse_repository(URL)
    assert [(s.name, s.files) for s in contents.skills] == [("expenses", ["scripts/add.py"]), ("news-digest", [])]
    hello, tasks = contents.servers
    assert (hello.name, hello.transport, [f.key for f in hello.fields]) == (
        "hello",
        "stdio",
        ["HELLO_USER", "HELLO_TOKEN"],
    )
    assert hello.fields[1].secret and hello.fields[1].help == "https://example.com/token"
    assert (tasks.name, tasks.transport) == ("tasks", "http")
    assert not (isolated_settings / "skills").exists() and not (isolated_settings / "mcp").exists()


async def test_skills_are_installed_with_visible_files_and_their_source(service, repo, isolated_settings):
    installed = await service.install_from_repository(URL, ["expenses"], [])
    [skill] = installed.skills
    assert (skill.name, skill.files, skill.source) == ("expenses", ["scripts/add.py"], URL)
    assert not (isolated_settings / "skills" / "expenses" / "link.py").exists()
    assert store.installed_from("expenses") == Source(URL, "other/general/expenses", "head1")


async def test_an_installed_local_server_runs_from_its_folder_with_the_values_given(service, repo, isolated_settings):
    installed = await service.install_from_repository(URL, [], [HELLO])
    [status] = installed.servers
    assert (status.source, status.env_keys) == (URL, ["HELLO_GREETING", "HELLO_TOKEN", "HELLO_USER"])
    record = await servers.load(service.store, "hello")
    # The values given are keys, encrypted apart from the record (core/mcp/keys.py).
    assert record.env == {"HELLO_GREETING": "hi", "HELLO_USER": "", "HELLO_TOKEN": ""}
    server = await keys.fill(service.store, service.secrets, record)
    folder = isolated_settings / "mcp" / "hello"
    assert server.args == [f"{folder}/server.py"] and server.env["HELLO_USER"] == "Ana"
    assert [t.name for t in (await service.probe_mcp_server(server)).tools] == ["whoami"]


async def test_a_remote_server_gets_its_fields_as_headers(service, repo):
    await service.install_from_repository(URL, [], [ServerValues("tasks", {"Authorization": "Bearer t"})])
    server = await keys.fill(service.store, service.secrets, await servers.load(service.store, "tasks"))
    assert (server.url, server.headers) == ("https://tasks.example.com/mcp", {"Authorization": "Bearer t"})


async def test_everything_is_checked_before_anything_is_written(service, repo, isolated_settings):
    with pytest.raises(McpServerError, match="hello needs Token"):
        await service.install_from_repository(URL, ["expenses"], [ServerValues("hello", {"HELLO_USER": "Ana"})])
    assert not (isolated_settings / "skills" / "expenses").exists() and await servers.load_all(service.store) == []
    with pytest.raises(McpServerError, match="no MCP server named nope"):
        await service.install_from_repository(URL, [], [ServerValues("nope")])
    with pytest.raises(RepositoryError, match="Pick at least one"):
        await service.install_from_repository(URL, [], [])


async def test_names_taken_by_other_skills_or_servers_are_refused(service, repo):
    store.save("expenses", "Mine", "My steps")
    with pytest.raises(store.SkillError, match="already have a skill named expenses"):
        await service.install_from_repository(URL, ["expenses"], [])
    await service.add_mcp_server(McpServer("hello", command="mine"))
    with pytest.raises(McpServerError, match="already an MCP server named hello"):
        await service.install_from_repository(URL, [], [HELLO])
    assert store.load("expenses").description == "Mine"


async def test_updating_a_server_keeps_the_values_and_choices_of_the_user(service, repo):
    await service.install_from_repository(URL, [], [HELLO])
    await service.update_mcp_server("hello", McpServerChanges(trusted=True, include=["whoami"]))
    (repo / "other" / "general" / "hello" / "server.yaml").write_text(
        _MANIFEST.replace("HELLO_GREETING: hi", "HELLO_GREETING: hello")
    )
    status = await service.update_mcp_server_from_repository("hello")
    server = await keys.fill(service.store, service.secrets, await servers.load(service.store, "hello"))
    assert (server.env["HELLO_GREETING"], server.env["HELLO_USER"]) == ("hello", "Ana")
    assert (status.trusted, status.include) == (True, ["whoami"])


async def test_a_server_whose_new_version_needs_a_new_value_isnt_updated(service, repo):
    await service.install_from_repository(URL, [], [HELLO])
    manifest = _MANIFEST + "  - {key: HELLO_CITY, label: Your city}\n"
    (repo / "other" / "general" / "hello" / "server.yaml").write_text(manifest)
    with pytest.raises(McpServerError, match="needs Your city: remove it and install it again"):
        await service.update_mcp_server_from_repository("hello")
    await service.add_mcp_server(McpServer("mine", command="mine"))
    with pytest.raises(McpServerError, match="wasn't installed"):
        await service.update_mcp_server_from_repository("mine")


async def test_removing_an_installed_server_deletes_its_folder_and_keeps_its_data(service, repo, isolated_settings):
    data = isolated_settings / "data" / "hello"
    await service.install_from_repository(URL, [], [HELLO])
    data.mkdir(parents=True, exist_ok=True)
    (data / "expenses.db").write_text("kept")
    await service.remove_mcp_server("hello")
    assert not (isolated_settings / "mcp" / "hello").exists() and (data / "expenses.db").exists()


async def test_removing_a_server_can_delete_its_data_too(service, repo, isolated_settings):
    data = isolated_settings / "data" / "hello"
    await service.install_from_repository(URL, [], [HELLO])
    data.mkdir(parents=True, exist_ok=True)
    (data / "expenses.db").write_text("gone")
    await service.remove_mcp_server("hello", delete_data=True)
    assert not data.exists()


async def test_a_plugin_that_cant_be_read_is_left_out_and_the_rest_listed(service, repo):
    _write(repo / "apps" / "finance" / "ledger", {"server.yaml": "description: Money: in and out\ncommand: x"})
    contents = await service.browse_repository(URL)
    assert "hello" in [s.name for s in contents.servers] and "ledger" not in [s.name for s in contents.servers]
    [problem] = contents.problems
    assert problem.startswith("apps/finance/ledger/server.yaml can't be used: mapping values are not allowed")
    await service.install_from_repository(URL, [], [HELLO])


async def test_a_server_yaml_that_cant_work_is_reported(service, repo):
    (repo / "other" / "general" / "tasks" / "server.yaml").write_text("command: run\nurl: https://x")
    assert re.search(r"other/general/tasks/server\.yaml can.t be used: Give either a command", await _problems(service))


async def test_updating_a_skill_replaces_local_changes(service, repo, isolated_settings):
    await service.install_from_repository(URL, ["expenses"], [])
    store.save("expenses", "Mine", "My steps", {"scripts/mine.py": "x"})
    (repo / "other" / "general" / "expenses" / "scripts" / "add.py").write_text("print('v2')")
    skill = await skill_install.update("expenses")
    assert skill.description == "Track expenses" and skill.files == ["scripts/add.py"]
    assert (isolated_settings / "skills" / "expenses" / "scripts" / "add.py").read_text() == "print('v2')"
    store.save("hand-made", "Mine", "My steps")
    with pytest.raises(store.SkillError, match="wasn't installed"):
        await skill_install.update("hand-made")


async def test_a_repository_that_is_one_skill_is_named_after_it(service, tmp_path, monkeypatch):
    root = tmp_path / "single"
    _skill(root, None, "Single", {"run.sh": "echo hi"})

    async def fetch(url: str, dest: Path, token: str = "") -> str:
        shutil.copytree(root, dest)
        return "c1"

    monkeypatch.setattr(checkout, "_fetch", fetch)
    installed = await service.install_from_repository(
        "https://example.com/me/Weather-Report.git", ["weather-report"], []
    )
    source = store.installed_from("weather-report")
    assert installed.skills[0].files == ["run.sh"] and source is not None and source.path == "."


@pytest.mark.parametrize("url", ["file:///tmp/repo", "ext::sh -c touch% /tmp/x", "git@github.com:me/x.git", ""])
async def test_only_https_repositories_are_downloaded(service, url):
    with pytest.raises(RepositoryError, match="https://"):
        await service.browse_repository(url)


_WITH_PAGE = """
name: ledger
command: "{uv}"
args: [run, --project, "{dir}", ledger-mcp]
env: {LEDGER_DB: "{data}/ledger.db"}
page:
  command: "{uv}"
  args: [run, --project, "{dir}", ledger-web, --socket, "{socket}"]
"""


async def test_a_server_gets_its_folders_uv_and_page_filled_in(service, repo, isolated_settings, monkeypatch):
    from assistant.core.mcp import install as server_install

    monkeypatch.setattr(server_install, "find_uv", lambda: "/opt/uv")
    _write(repo / "other" / "general" / "ledger", {"server.yaml": _WITH_PAGE})
    [status] = (await service.install_from_repository(URL, [], [ServerValues("ledger")])).servers
    server = await servers.load(service.store, "ledger")
    code, data = isolated_settings / "mcp" / "ledger", isolated_settings / "data" / "ledger"
    assert (server.command, server.args) == ("/opt/uv", ["run", "--project", str(code), "ledger-mcp"])
    assert server.env == {"LEDGER_DB": f"{data}/ledger.db"}
    assert server.page_args[-1] == f"{data}/page.sock" and status.page
    assert data.is_dir() and data.stat().st_mode & 0o777 == 0o700
    (data / "ledger.db").write_text("kept")
    await service.remove_mcp_server("ledger")
    assert not code.exists() and (data / "ledger.db").read_text() == "kept"


async def test_a_server_that_runs_with_uv_needs_uv(service, repo, monkeypatch):
    from assistant.core.mcp import install as server_install

    monkeypatch.setattr(server_install, "find_uv", lambda: None)
    _write(repo / "other" / "general" / "ledger", {"server.yaml": _WITH_PAGE})
    with pytest.raises(McpServerError, match="can't find uv"):
        await service.install_from_repository(URL, [], [ServerValues("ledger")])


_IN_ENVIRONMENT = """
name: ledger
format: 2
command: "{bin}/ledger-mcp"
page:
  command: "{bin}/ledger-web"
  args: [--socket, "{socket}"]
"""
_PROJECT = """
[project]
name = "ledger"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[tool.uv]
package = false
"""


async def test_a_server_runs_from_its_own_environment_built_when_installed(service, repo, isolated_settings):
    """One process per server: its scripts run directly, not under `uv run`."""
    folder = repo / "other" / "general" / "ledger"
    _write(folder, {"server.yaml": _IN_ENVIRONMENT, "pyproject.toml": _PROJECT})
    lock = await asyncio.create_subprocess_exec(find_uv() or "uv", "lock", "--offline", "--quiet", cwd=folder)
    assert await lock.wait() == 0
    await service.install_from_repository(URL, [], [ServerValues("ledger")])
    server = await servers.load(service.store, "ledger")
    scripts = isolated_settings / "mcp" / "ledger" / ".venv" / "bin"
    assert (server.command, server.page_command) == (f"{scripts}/ledger-mcp", f"{scripts}/ledger-web")
    assert (scripts / "python").exists()


async def test_a_server_with_an_environment_needs_uv(service, repo, monkeypatch):
    from assistant.core.mcp import install as server_install

    monkeypatch.setattr(server_install, "find_uv", lambda: None)
    _write(repo / "other" / "general" / "ledger", {"server.yaml": _IN_ENVIRONMENT})
    with pytest.raises(McpServerError, match="can't find uv"):
        await service.install_from_repository(URL, [], [ServerValues("ledger")])


async def test_a_server_in_a_newer_format_than_the_daemon_reads_isnt_found(service, repo):
    _write(repo / "other" / "general" / "ledger", {"server.yaml": _IN_ENVIRONMENT.replace("format: 2", "format: 4")})
    assert "ledger" not in [s.name for s in (await service.browse_repository(URL)).servers]


async def test_a_server_using_bin_must_say_its_format(service, repo):
    _write(repo / "other" / "general" / "ledger", {"server.yaml": _IN_ENVIRONMENT.replace("format: 2\n", "")})
    assert re.search("needs format: 2", await _problems(service))


_HELLO_SKILL = "---\nname: hello\ndescription: Greeting people\n---\n\nCall whoami first."


async def test_a_servers_skill_is_installed_updated_and_removed_with_it(service, repo, isolated_settings):
    _write(repo / "other" / "general" / "hello", {"SKILL.md": _HELLO_SKILL})
    contents = await service.browse_repository(URL)
    assert "hello" not in [s.name for s in contents.skills]
    assert next(s for s in contents.servers if s.name == "hello").skill
    await service.install_from_repository(URL, [], [HELLO])
    skill = store.load("hello")
    assert (skill.server, skill.instructions, skill.files) == ("hello", "Call whoami first.", [])
    assert sorted(p.name for p in (isolated_settings / "skills" / "hello").iterdir()) == [".source.yaml", "SKILL.md"]

    with pytest.raises(store.SkillError, match="comes with the hello MCP server"):
        await service.delete_skill("hello")
    with pytest.raises(store.SkillError, match="update the server"):
        await skill_install.update("hello")

    _write(repo / "other" / "general" / "hello", {"SKILL.md": _HELLO_SKILL.replace("whoami first", "whoami")})
    await service.update_mcp_server_from_repository("hello")
    assert store.load("hello").instructions == "Call whoami."
    (repo / "other" / "general" / "hello" / "SKILL.md").unlink()
    await service.update_mcp_server_from_repository("hello")
    with pytest.raises(store.SkillError, match="No skill"):
        store.load("hello")

    _write(repo / "other" / "general" / "hello", {"SKILL.md": _HELLO_SKILL})
    await service.update_mcp_server_from_repository("hello")
    await service.remove_mcp_server("hello")
    with pytest.raises(store.SkillError, match="No skill"):
        store.load("hello")


async def test_a_servers_skill_needs_its_name_free_and_matching(service, repo):
    _write(repo / "other" / "general" / "hello", {"SKILL.md": _HELLO_SKILL})
    store.save("hello", "Mine", "My steps")
    with pytest.raises(McpServerError, match="already have a skill named hello"):
        await service.install_from_repository(URL, [], [HELLO])
    assert store.load("hello").description == "Mine"
    _write(repo / "other" / "general" / "hello", {"SKILL.md": _HELLO_SKILL.replace("name: hello", "name: greeter")})
    assert re.search(r"SKILL\.md must be named hello", await _problems(service))


async def test_a_top_level_server_folder_is_not_also_a_skill(service, repo):
    _write(repo / "solo", {"server.yaml": "command: run-solo", "SKILL.md": "---\nname: solo\n---\n\nUse it."})
    contents = await service.browse_repository(URL)
    assert "solo" not in [s.name for s in contents.skills]
    assert next(s for s in contents.servers if s.name == "solo").skill


async def test_a_plugins_folder_gives_its_category(service, repo):
    _write(repo / "apps" / "finance" / "ledger", {"server.yaml": "url: https://ledger.example.com/mcp"})
    _write(repo / "communications" / "contacts" / "people", {"server.yaml": "url: https://people.example.com/mcp"})
    _write(repo / "productivity" / "calendar" / "agenda", {"server.yaml": "url: https://agenda.example.com/mcp"})
    _skill(repo / "communications" / "chat" / "digest", "digest", "Daily digest", {})
    contents = await service.browse_repository(URL)
    assert {s.name: s.category for s in contents.servers} == {
        "hello": "other/general",
        "ledger": "apps/finance",
        "people": "communications/contacts",
        "agenda": "productivity/calendar",
        "tasks": "other/general",
    }
    assert {s.name: s.category for s in contents.skills}["digest"] == "communications/chat"


async def test_outside_a_category_folder_a_plugin_declares_it(service, repo):
    _write(repo / "ledger", {"server.yaml": "url: https://ledger.example.com/mcp\ncategory: apps/finance"})
    _write(repo / "plain", {"server.yaml": "url: https://plain.example.com/mcp"})
    contents = await service.browse_repository(URL)
    assert {s.name: s.category for s in contents.servers if s.name in ("ledger", "plain")} == {
        "ledger": "apps/finance",
        "plain": "other/general",
    }


async def test_a_category_that_disagrees_with_its_folder_is_refused(service, repo):
    _write(
        repo / "apps" / "finance" / "ledger",
        {"server.yaml": "url: https://ledger.example.com/mcp\ncategory: other/general"},
    )
    assert re.search("it's in the apps/finance folder, but its category says other/general", await _problems(service))


async def test_a_category_not_in_the_list_is_refused(service, repo):
    _write(repo / "tasks2", {"server.yaml": "url: https://tasks.example.com/mcp\ncategory: chat"})
    assert re.search(
        "its category 'chat' isn't one of apps/finance, apps/media, assistant/agents", await _problems(service)
    )


@pytest.mark.parametrize("system", ["darwin", "linux"])
async def test_plugins_for_another_system_arent_listed_or_installed(service, repo, monkeypatch, system):
    monkeypatch.setattr("assistant.core.repositories.platforms.sys.platform", system)
    _write(repo / "phone", {"server.yaml": "url: https://phone.example.com/mcp\nplatforms: [macos]"})
    _write(repo / "anywhere", {"server.yaml": "url: https://anywhere.example.com/mcp\nplatforms: [linux, macos]"})
    _write(
        repo / "linux-tool", {"SKILL.md": "---\nname: linux-tool\ndescription: Linux\nplatforms: linux\n---\n\nSteps."}
    )
    contents = await service.browse_repository(URL)
    servers_here = {s.name for s in contents.servers}
    skills_here = {s.name for s in contents.skills}
    assert "anywhere" in servers_here
    assert ("phone" in servers_here) == (system == "darwin")
    assert ("linux-tool" in skills_here) == (system == "linux")
    if system == "linux":
        with pytest.raises(McpServerError, match="has no MCP server named phone"):
            await service.install_from_repository(URL, [], [ServerValues("phone")])


async def test_a_platform_not_in_the_list_is_refused(service, repo):
    _write(repo / "phone", {"server.yaml": "url: https://phone.example.com/mcp\nplatforms: [windows]"})
    assert re.search("its platforms windows aren't any of linux, macos", await _problems(service))


def test_a_skill_with_a_platform_not_in_the_list_has_a_problem(tmp_path):
    _write(tmp_path / "x", {"SKILL.md": "---\nname: x\ndescription: X\nplatforms: [beos]\n---\n\nSteps."})
    skill = store.read(tmp_path / "x")
    assert skill is not None
    assert skill.problems == ["In its SKILL.md, its platforms beos aren't any of linux, macos."]


async def test_an_update_that_drops_this_system_keeps_the_installed_version(service, repo, monkeypatch):
    monkeypatch.setattr("assistant.core.repositories.platforms.sys.platform", "linux")
    await service.install_from_repository(URL, ["expenses"], [])
    manifest = repo / "other" / "general" / "expenses" / "SKILL.md"
    manifest.write_text(manifest.read_text().replace("description:", "platforms: [macos]\ndescription:"))
    REMOTE["head"] = "head2"
    with pytest.raises(SkillError, match="The new version of expenses doesn't run on linux"):
        await service.update_installed_skill("expenses")


async def test_a_server_can_ask_for_the_copilot_login_and_leave_a_field_optional(service, repo):
    manifest = (
        'command: "{python}"\nargs: ["{dir}/server.py"]\nmodel_login: copilot\n'
        "fields:\n  - {key: CLAUDE_TOKEN, label: Claude token, secret: true, optional: true}\n"
    )
    _write(repo / "coder", {"server.yaml": manifest, "server.py": _SERVER})
    found = next(s for s in (await service.browse_repository(URL)).servers if s.name == "coder")
    assert found.model_login == "copilot" and found.fields[0].optional
    await service.install_from_repository(URL, [], [ServerValues("coder", {})])
    assert (await servers.load(service.store, "coder")).model_login == "copilot"


async def test_a_plugin_can_bring_an_agent_with_its_command_and_worker(service, repo):
    manifest = "format: 3\nagent: {command: claude, name: Claude Code, worker: '{python}', args: ['{dir}/worker.py']}\n"
    _write(repo / "coder", {"server.yaml": manifest, "worker.py": ""})
    found = next(s for s in (await service.browse_repository(URL)).servers if s.name == "coder")
    assert (found.agent, found.transport) == ("claude", "none")
    await service.install_from_repository(URL, [], [ServerValues("coder", {})])
    assert [(a.command, a.name) for a in await service.agents()] == [("claude", "Claude Code")]
    assert [a.name for a in service.agent_tasks.agents()] == ["Claude Code"]


@pytest.mark.parametrize(
    ("agent", "problem"),
    [
        ("{command: claude, name: Claude Code}", "must have command, name and worker"),
        ("{command: Claude!, name: X, worker: w}", "must be a lowercase word"),
    ],
)
async def test_an_agent_section_that_cant_work_is_refused(service, repo, agent, problem):
    _write(repo / "coder", {"server.yaml": f"url: https://coder.example.com/mcp\nagent: {agent}"})
    assert re.search(problem, await _problems(service))


async def test_an_unknown_model_login_is_refused(service, repo):
    _write(repo / "coder", {"server.yaml": "url: https://coder.example.com/mcp\nmodel_login: claude"})
    assert re.search("its model_login 'claude' isn't one of copilot", await _problems(service))


async def test_a_server_can_ask_for_the_ssh_agent_with_true_or_false(service, repo):
    _write(repo / "remote", {"server.yaml": "url: https://remote.example.com/mcp\nssh_agent: true"})
    _write(
        repo / "other" / "general" / "odd", {"server.yaml": "url: https://odd.example.com/mcp\nssh_agent: yes-please"}
    )
    found = next(s for s in (await service.browse_repository(URL)).servers if s.name == "remote")
    assert found.ssh_agent
    assert re.search("its ssh_agent must be true or false", await _problems(service))
    await service.install_from_repository(URL, [], [ServerValues("remote", {})])
    assert (await servers.load(service.store, "remote")).ssh_agent


async def test_a_channel_is_in_communications(service, repo):
    _write(repo / "bot", {"server.yaml": "channel: {command: run-bot}"})
    contents = await service.browse_repository(URL)
    assert next(s for s in contents.servers if s.name == "bot").category == "communications/chat"
    _write(repo / "apps" / "finance" / "bot2", {"server.yaml": "channel: {command: run-bot}"})
    REMOTE["head"] = "head2"
    assert re.search("it's a channel plugin, so its category must be communications/chat", await _problems(service))


_GMAIL = """
email:
  - {id: gmail, name: Gmail, host: smtp.gmail.com, port: 587, imap_host: imap.gmail.com}
  - {id: gmail-oauth, name: Gmail (sign in with Google), host: smtp.gmail.com, imap_host: imap.gmail.com, oauth: google}
"""


async def test_an_email_plugin_offers_its_providers_once_installed(service, repo):
    _write(repo / "communications" / "email" / "gmail", {"server.yaml": _GMAIL})
    found = next(s for s in (await service.browse_repository(URL)).servers if s.name == "gmail")
    assert (found.email, found.transport, found.category) == (True, "none", "communications/email")
    await service.install_from_repository(URL, [], [ServerValues("gmail")])
    assert [(p.id, p.oauth, p.plugin) for p in await service.email_providers()] == [
        ("gmail", "", "gmail"),
        ("gmail-oauth", "google", "gmail"),
    ]


async def test_a_custom_email_plugin_takes_the_accounts_that_belong_to_no_plugin(service, repo, monkeypatch):
    from assistant.core.integrations.email import smtp

    async def verify(config):
        pass

    monkeypatch.setattr(smtp, "verify", verify)
    by_hand = await service.add_email_account("", "smtp.example.com", 587, "me", "pw", "me@example.com")
    custom = "email:\n  - {id: custom, name: Other server, custom: true, password_help: Use an app password.}"
    _write(repo / "communications" / "email" / "custom-email", {"server.yaml": custom})
    await service.install_from_repository(URL, [], [ServerValues("custom-email")])
    [provider] = await service.email_providers()
    assert (provider.id, provider.custom, provider.host, provider.plugin) == ("custom", True, "", "custom-email")
    [account] = await service.email_accounts()
    assert (account.id, account.plugin) == (by_hand.id, "custom-email")
    await service.update_mcp_server("custom-email", McpServerChanges(enabled=False))
    assert await service.email_accounts() == []  # its plugin is off


async def test_a_plugins_steps_come_with_it_for_the_install_dialogs(service, repo):
    yaml = "channel: {command: run-bot}\nsteps:\n  - Open @BotFather and send /newbot.\n  - Paste the token below.\n"
    _write(repo / "communications" / "chat" / "bot", {"server.yaml": yaml})
    found = next(s for s in (await service.browse_repository(URL)).servers if s.name == "bot")
    assert found.steps == ["Open @BotFather and send /newbot.", "Paste the token below."]


async def test_a_plugin_the_repository_moved_still_updates(service, repo):
    _write(repo / "gmail", {"server.yaml": _GMAIL})
    await service.install_from_repository(URL, [], [ServerValues("gmail")])
    (repo / "communications" / "email").mkdir(parents=True)
    (repo / "gmail").rename(repo / "communications" / "email" / "gmail")
    await service.update_mcp_server_from_repository("gmail")
    assert [p.id for p in await service.email_providers()] == ["gmail", "gmail-oauth"]


@pytest.mark.parametrize(
    ("section", "problem"),
    [
        ("email: {id: gmail}", "must be a list of providers"),
        ("email: [{id: gmail, name: Gmail}]", "has no host, imap_host"),
        ("email: [{id: custom, custom: true}]", "has no name"),
        ("email: [{id: g, name: G, host: s, imap_host: i, oauth: yahoo}]", "signs in with 'yahoo'"),
    ],
)
async def test_an_email_section_that_cant_work_is_reported(service, repo, section, problem):
    _write(repo / "communications" / "email" / "gmail", {"server.yaml": section})
    assert re.search(problem, await _problems(service))


async def test_a_skill_with_an_unknown_category_has_a_problem_and_isnt_installed(service, repo):
    _skill(repo / "notes", "notes", "Notes\ncategory: chat", {})
    with pytest.raises(SkillError, match="its category 'chat' isn't one of"):
        await service.install_from_repository(URL, ["notes"], [])


async def test_a_skill_whose_category_disagrees_with_its_folder_isnt_installed(service, repo):
    _skill(repo / "other" / "general" / "news", "news-digest", "Daily news\ncategory: communications/chat", {})
    with pytest.raises(
        SkillError, match=r"in the other/general folder, but its SKILL\.md says category communications/chat"
    ):
        await service.install_from_repository(URL, ["news-digest"], [])


async def test_browsing_says_what_is_installed_from_that_repository(service, repo):
    store.save("news-digest", "Mine", "My steps")
    await service.install_from_repository(URL, ["expenses"], [HELLO])
    contents = await service.browse_repository(URL)
    assert {s.name: s.installed for s in contents.skills} == {"expenses": True, "news-digest": False}
    assert {s.name: s.installed for s in contents.servers} == {"hello": True, "tasks": False}


async def test_the_listing_is_kept_until_the_repository_has_a_newer_commit(service, repo):
    await service.browse_repository(URL)
    await service.browse_repository(URL)
    assert REMOTE["downloads"] == 1
    _write(repo / "other" / "general" / "later", {"SKILL.md": "---\nname: later\ndescription: New\n---\n\nSteps."})
    REMOTE["head"] = "head2"
    contents = await service.browse_repository(URL)
    assert REMOTE["downloads"] == 2 and "later" in [s.name for s in contents.skills]


async def test_an_unreachable_repository_shows_the_kept_listing(service, repo):
    REMOTE["head"] = None
    with pytest.raises(RepositoryError, match="no network"):
        await service.browse_repository(URL)
    REMOTE["head"] = "head1"
    await service.browse_repository(URL)
    REMOTE["head"] = None
    await service.install_from_repository(URL, ["expenses"], [])
    contents = await service.browse_repository(URL)
    assert {s.name: s.installed for s in contents.skills}["expenses"]  # installed is read fresh, not kept


async def test_versions_say_what_is_installed_and_what_is_newer(service, repo):
    manifest = repo / "other" / "general" / "hello" / "server.yaml"
    manifest.write_text("version: 1.0.0\n" + manifest.read_text())
    await service.install_from_repository(URL, [], [HELLO])
    manifest.write_text(manifest.read_text().replace("version: 1.0.0", "version: 1.1.0"))
    REMOTE["head"] = "head2"
    hello = next(s for s in (await service.browse_repository(URL)).servers if s.name == "hello")
    assert (hello.version, hello.installed_version) == ("1.1.0", "1.0.0")
    await service.update_mcp_server_from_repository("hello")
    hello = next(s for s in (await service.browse_repository(URL)).servers if s.name == "hello")
    assert hello.installed_version == "1.1.0"


async def test_what_a_plugin_added_is_told_apart_from_what_was_added_here(service, repo):
    _write(repo / "other" / "general" / "hello", {"SKILL.md": _HELLO_SKILL})
    await service.install_from_repository(URL, ["expenses"], [HELLO])
    await service.add_mcp_server(McpServer("mine", command="mine"))
    store.save("notes", "Mine", "My steps")
    by_server = {s.name: s.plugin for s in await service.mcp_servers()}
    assert by_server == {"hello": "hello", "mine": ""}
    by_skill = {s.name: s.plugin for s in await service.list_skills()}
    assert by_skill == {"expenses": "expenses", "hello": "hello", "notes": ""}


async def test_the_assistant_cant_delete_a_skill_a_plugin_installed(service, repo, script):
    from assistant.core.events import ToolFinished
    from tests.conftest import collect

    await service.install_from_repository(URL, ["expenses"], [])
    script.call("delete_skill", name="expenses").reply("can't")
    events = await collect(service.send(await service.session("u", "cli"), "delete the expenses skill"))
    [finished] = [e for e in events if isinstance(e, ToolFinished)]
    assert "installed by the expenses plugin" in finished.output and "expenses" in [s.name for s in store.list_skills()]


async def test_the_icon_reaches_the_listing_the_installed_server_and_its_status(service, repo):
    manifest = (repo / "other" / "general" / "hello" / "server.yaml").read_text()
    _write(repo / "other" / "general" / "hello", {"server.yaml": manifest + "icon: icon.svg\n", "icon.svg": BRAND})
    _write(repo / "apps" / "media" / "films", {"server.yaml": "url: https://films.example.com/mcp\nicon: tv"})
    _skill(repo / "apps" / "finance" / "budget", "budget", "Budget", {})
    contents = await service.browse_repository(URL)
    by_name = {s.name: s.icon for s in contents.servers}
    assert by_name["hello"] == PluginIcon(svg=BRAND) and by_name["films"] == PluginIcon(name="tv")
    assert by_name["tasks"] == PluginIcon(name="puzzle")  # other/general's
    assert {s.name: s.icon for s in contents.skills}["budget"] == PluginIcon(name="wallet")
    await service.install_from_repository(URL, [], [HELLO])
    assert (await servers.load(service.store, "hello")).icon == {"name": "", "svg": BRAND, "mono": False}
    [status] = [s for s in await service.mcp_servers() if s.name == "hello"]
    assert status.icon == PluginIcon(svg=BRAND)


async def test_a_server_installed_before_icons_gets_its_icon_from_its_folder_at_start(service, repo):
    manifest = (repo / "other" / "general" / "hello" / "server.yaml").read_text()
    _write(repo / "other" / "general" / "hello", {"server.yaml": manifest + "icon: icon.svg\n", "icon.svg": BRAND})
    _write(repo / "apps" / "media" / "films", {"server.yaml": "url: https://films.example.com/mcp"})
    await service.install_from_repository(URL, [], [HELLO, ServerValues("films")])
    for name in ("hello", "films"):
        await servers.save(service.store, replace(await servers.load(service.store, name), icon={}))
    await servers.save(service.store, McpServer("mine", url="https://mine.example.com/mcp"))
    await install.add_missing_icons(service.store, service.secrets)
    assert (await servers.load(service.store, "hello")).icon == {"name": "", "svg": BRAND, "mono": False}
    assert (await servers.load(service.store, "films")).icon == {"name": "clapperboard", "svg": "", "mono": False}
    assert (await servers.load(service.store, "mine")).icon == {}
    assert (await keys.fill(service.store, service.secrets, await servers.load(service.store, "hello"))).env[
        "HELLO_TOKEN"
    ] == "s3cret"


async def test_a_plugin_with_an_icon_that_cant_be_used_is_left_out_with_why(service, repo):
    _write(repo / "apps" / "media" / "films", {"server.yaml": "url: https://films.example.com/mcp\nicon: nope"})
    shows = "---\nname: shows\ndescription: Shows\nicon: x.svg\n---\nSteps."
    _write(repo / "apps" / "media" / "shows", {"SKILL.md": shows})
    contents = await service.browse_repository(URL)
    assert "films" not in {s.name for s in contents.servers}
    assert any("'nope' isn't a Lucide icon" in p for p in contents.problems)
    # A skill's problems are its own, as with its header: the check before a push says them.
    assert any("x.svg isn't a file in its folder" in p for p in check.problems(repo))
