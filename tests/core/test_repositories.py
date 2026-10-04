"""Installing skills and MCP servers from a git repository. The download is replaced by a copy of a
local folder; installed local servers really run."""

import shutil
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

    async def fetch(url: str, dest: Path) -> str:
        REMOTE["downloads"] += 1
        shutil.copytree(root, dest, symlinks=True)
        return REMOTE["head"] or "head1"

    async def latest_commit(url: str) -> str:
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
    assert store.installed_from("expenses") == Source(URL, "skills/expenses", "head1")


async def test_an_installed_local_server_runs_from_its_folder_with_the_values_given(service, repo, isolated_settings):
    installed = await service.install_from_repository(URL, [], [HELLO])
    [status] = installed.servers
    assert (status.source, status.env_keys) == (URL, ["HELLO_GREETING", "HELLO_TOKEN", "HELLO_USER"])
    server = await servers.load(service.store, "hello")
    folder = isolated_settings / "mcp" / "hello"
    assert server.args == [f"{folder}/server.py"] and server.env["HELLO_USER"] == "Ana"
    assert [t.name for t in (await service.probe_mcp_server(server)).tools] == ["whoami"]


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
    _write(repo / "mcp" / "ledger", {"server.yaml": _WITH_PAGE})
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
    _write(repo / "mcp" / "ledger", {"server.yaml": _WITH_PAGE})
    with pytest.raises(McpServerError, match="can't find uv"):
        await service.install_from_repository(URL, [], [ServerValues("ledger")])


_HELLO_SKILL = "---\nname: hello\ndescription: Greeting people\n---\n\nCall whoami first."


async def test_a_servers_skill_is_installed_updated_and_removed_with_it(service, repo, isolated_settings):
    _write(repo / "mcp" / "hello", {"SKILL.md": _HELLO_SKILL})
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

    _write(repo / "mcp" / "hello", {"SKILL.md": _HELLO_SKILL.replace("whoami first", "whoami")})
    await service.update_mcp_server_from_repository("hello")
    assert store.load("hello").instructions == "Call whoami."
    (repo / "mcp" / "hello" / "SKILL.md").unlink()
    await service.update_mcp_server_from_repository("hello")
    with pytest.raises(store.SkillError, match="No skill"):
        store.load("hello")

    _write(repo / "mcp" / "hello", {"SKILL.md": _HELLO_SKILL})
    await service.update_mcp_server_from_repository("hello")
    await service.remove_mcp_server("hello")
    with pytest.raises(store.SkillError, match="No skill"):
        store.load("hello")


async def test_a_servers_skill_needs_its_name_free_and_matching(service, repo):
    _write(repo / "mcp" / "hello", {"SKILL.md": _HELLO_SKILL})
    store.save("hello", "Mine", "My steps")
    with pytest.raises(McpServerError, match="already have a skill named hello"):
        await service.install_from_repository(URL, [], [HELLO])
    assert store.load("hello").description == "Mine"
    _write(repo / "mcp" / "hello", {"SKILL.md": _HELLO_SKILL.replace("name: hello", "name: greeter")})
    with pytest.raises(RepositoryError, match=r"SKILL\.md must be named hello"):
        await service.browse_repository(URL)


async def test_a_top_level_server_folder_is_not_also_a_skill(service, repo):
    _write(repo / "solo", {"server.yaml": "command: run-solo", "SKILL.md": "---\nname: solo\n---\n\nUse it."})
    contents = await service.browse_repository(URL)
    assert "solo" not in [s.name for s in contents.skills]
    assert next(s for s in contents.servers if s.name == "solo").skill


async def test_plugins_say_their_category_or_are_in_other(service, repo):
    _write(repo / "mcp" / "tasks", {"server.yaml": "url: https://tasks.example.com/mcp\ncategory: finance"})
    _skill(repo / "skills" / "news", "news-digest", "Daily news\ncategory: communications", {})
    contents = await service.browse_repository(URL)
    assert {s.name: s.category for s in contents.servers} == {"hello": "other", "tasks": "finance"}
    assert {s.name: s.category for s in contents.skills} == {"expenses": "other", "news-digest": "communications"}


async def test_a_category_not_in_the_list_is_refused(service, repo):
    _write(repo / "mcp" / "tasks", {"server.yaml": "url: https://tasks.example.com/mcp\ncategory: chat"})
    with pytest.raises(RepositoryError, match="its category 'chat' isn't one of communications, finance, other"):
        await service.browse_repository(URL)


async def test_a_channel_is_in_communications(service, repo):
    _write(repo / "mcp" / "tasks", {"server.yaml": "channel: {command: run-bot}"})
    contents = await service.browse_repository(URL)
    assert next(s for s in contents.servers if s.name == "tasks").category == "communications"
    _write(repo / "mcp" / "tasks", {"server.yaml": "channel: {command: run-bot}\ncategory: finance"})
    REMOTE["head"] = "head2"
    with pytest.raises(RepositoryError, match="it's a channel plugin, so its category must be communications"):
        await service.browse_repository(URL)


_GMAIL = """
email:
  - {id: gmail, name: Gmail, host: smtp.gmail.com, port: 587, imap_host: imap.gmail.com}
  - {id: gmail-oauth, name: Gmail (sign in with Google), host: smtp.gmail.com, imap_host: imap.gmail.com, oauth: google}
"""


async def test_an_email_plugin_offers_its_providers_once_installed(service, repo):
    _write(repo / "mcp" / "gmail", {"server.yaml": _GMAIL})
    found = next(s for s in (await service.browse_repository(URL)).servers if s.name == "gmail")
    assert (found.email, found.transport, found.category) == (True, "none", "communications")
    await service.install_from_repository(URL, [], [ServerValues("gmail")])
    assert [(p.id, p.oauth, p.plugin) for p in await service.email_providers()] == [
        ("gmail", "", "gmail"),
        ("gmail-oauth", "google", "gmail"),
    ]


@pytest.mark.parametrize(
    ("section", "problem"),
    [
        ("email: {id: gmail}", "must be a list of providers"),
        ("email: [{id: gmail, name: Gmail}]", "has no host, imap_host"),
        ("email: [{id: g, name: G, host: s, imap_host: i, oauth: yahoo}]", "signs in with 'yahoo'"),
    ],
)
async def test_an_email_section_that_cant_work_is_reported(service, repo, section, problem):
    _write(repo / "mcp" / "gmail", {"server.yaml": section})
    with pytest.raises(RepositoryError, match=problem):
        await service.browse_repository(URL)


async def test_a_skill_with_an_unknown_category_has_a_problem_and_isnt_installed(service, repo):
    _skill(repo / "skills" / "news", "news-digest", "Daily news\ncategory: chat", {})
    with pytest.raises(SkillError, match="its category 'chat' isn't one of"):
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
    _write(repo / "skills" / "later", {"SKILL.md": "---\nname: later\ndescription: New\n---\n\nSteps."})
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
    manifest = repo / "mcp" / "hello" / "server.yaml"
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
    _write(repo / "mcp" / "hello", {"SKILL.md": _HELLO_SKILL})
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
