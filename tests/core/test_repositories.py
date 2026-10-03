"""Installing skills and MCP servers from a git repository. The download is replaced by a copy of a
local folder; installed local servers really run."""

import shutil
from pathlib import Path

import pytest

from assistant.core.agent import McpServer, McpServerChanges, McpServerError, RepositoryError, ServerValues
from assistant.core.mcp import servers
from assistant.core.repositories import checkout
from assistant.core.repositories.source import Source
from assistant.core.skills import install as skill_install
from assistant.core.skills import store

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
    """Two skills under skills/, a local and a remote server under mcp/, the way the download sees them."""
    root = tmp_path / "remote"
    _skill(root / "skills" / "expenses", "expenses", "Track expenses", {"scripts/add.py": "print('v1')"})
    _skill(root / "skills" / "news", "news-digest", "Daily news", {})
    _write(root / "mcp" / "hello", {"server.yaml": _MANIFEST, "server.py": _SERVER})
    _write(
        root / "mcp" / "tasks",
        {"server.yaml": "url: https://tasks.example.com/mcp\nfields: [{key: Authorization, label: Token}]"},
    )
    _write(root / ".git", {"config": "[core]"})
    (root / "skills" / "expenses" / "link.py").symlink_to("/etc/hosts")
    commits = iter(f"commit{i}" for i in range(1, 10))

    async def fetch(url: str, dest: Path) -> str:
        shutil.copytree(root, dest, symlinks=True)
        return next(commits)

    monkeypatch.setattr(checkout, "_fetch", fetch)
    return root


def _skill(folder: Path, name: str | None, description: str, files: dict[str, str]) -> None:
    header = f"---\nname: {name}\ndescription: {description}\n---\n\n" if name else ""
    _write(folder, {"SKILL.md": f"{header}Steps for {description}.", **files})


def _write(folder: Path, files: dict[str, str]) -> None:
    for path, content in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text(content)


HELLO = ServerValues("hello", {"HELLO_USER": "Ana", "HELLO_TOKEN": "s3cret"})


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
    assert store.installed_from("expenses") == Source(URL, "skills/expenses", "commit1")


async def test_an_installed_local_server_runs_from_its_folder_with_the_values_given(service, repo, isolated_settings):
    installed = await service.install_from_repository(URL, [], [HELLO])
    [status] = installed.servers
    assert (status.source, status.env_keys) == (URL, ["HELLO_GREETING", "HELLO_TOKEN", "HELLO_USER"])
    server = await servers.load(service.store, "hello")
    folder = isolated_settings / "mcp" / "hello"
    assert server.args == [f"{folder}/server.py"] and server.env["HELLO_USER"] == "Ana"
    assert [t.name for t in await service.probe_mcp_server(server)] == ["whoami"]


async def test_a_remote_server_gets_its_fields_as_headers(service, repo):
    await service.install_from_repository(URL, [], [ServerValues("tasks", {"Authorization": "Bearer t"})])
    server = await servers.load(service.store, "tasks")
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
    (repo / "mcp" / "hello" / "server.yaml").write_text(
        _MANIFEST.replace("HELLO_GREETING: hi", "HELLO_GREETING: hello")
    )
    status = await service.update_mcp_server_from_repository("hello")
    server = await servers.load(service.store, "hello")
    assert (server.env["HELLO_GREETING"], server.env["HELLO_USER"]) == ("hello", "Ana")
    assert (status.trusted, status.include) == (True, ["whoami"])


async def test_a_server_whose_new_version_needs_a_new_value_isnt_updated(service, repo):
    await service.install_from_repository(URL, [], [HELLO])
    manifest = _MANIFEST + "  - {key: HELLO_CITY, label: Your city}\n"
    (repo / "mcp" / "hello" / "server.yaml").write_text(manifest)
    with pytest.raises(McpServerError, match="needs Your city: remove it and install it again"):
        await service.update_mcp_server_from_repository("hello")
    await service.add_mcp_server(McpServer("mine", command="mine"))
    with pytest.raises(McpServerError, match="wasn't installed"):
        await service.update_mcp_server_from_repository("mine")


async def test_removing_an_installed_server_deletes_its_folder(service, repo, isolated_settings):
    await service.install_from_repository(URL, [], [HELLO])
    await service.remove_mcp_server("hello")
    assert not (isolated_settings / "mcp" / "hello").exists()


async def test_a_server_yaml_that_cant_work_is_reported(service, repo):
    (repo / "mcp" / "tasks" / "server.yaml").write_text("command: run\nurl: https://x")
    with pytest.raises(RepositoryError, match=r"mcp/tasks/server\.yaml can.t be used: Give either a command"):
        await service.browse_repository(URL)


async def test_updating_a_skill_replaces_local_changes(service, repo, isolated_settings):
    await service.install_from_repository(URL, ["expenses"], [])
    store.save("expenses", "Mine", "My steps", {"scripts/mine.py": "x"})
    (repo / "skills" / "expenses" / "scripts" / "add.py").write_text("print('v2')")
    skill = await skill_install.update("expenses")
    assert skill.description == "Track expenses" and skill.files == ["scripts/add.py"]
    assert (isolated_settings / "skills" / "expenses" / "scripts" / "add.py").read_text() == "print('v2')"
    store.save("hand-made", "Mine", "My steps")
    with pytest.raises(store.SkillError, match="wasn't installed"):
        await skill_install.update("hand-made")


async def test_a_repository_that_is_one_skill_is_named_after_it(service, tmp_path, monkeypatch):
    root = tmp_path / "single"
    _skill(root, None, "Single", {"run.sh": "echo hi"})

    async def fetch(url: str, dest: Path) -> str:
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
