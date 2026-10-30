"""The handed folder's routes: read only while the conversation is with an agent, only inside its folder."""

import subprocess

import httpx
import pytest

from assistant.client.daemon_client import DaemonClient
from assistant.core.agent import DeletingOffError, HandedFolderError, MissingPathError, Session
from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER
from tests.core.test_handoffs import agent_plugin


@pytest.fixture
async def http(service):
    await service.add_mcp_server(agent_plugin())
    transport = httpx.ASGITransport(app=trusted(create_app(service, RunHub())))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}) as h:
        yield h


@pytest.fixture
def client(http) -> DaemonClient:
    """As the terminal app reads the folder panel."""
    return DaemonClient(http)


async def _handed(service, folder) -> str:
    session = Session("owner", "cli", await service.new_thread("owner"))
    await service.hand_conversation("owner", session.thread_id, "claude", str(folder))
    return session.thread_id


async def test_the_folder_is_listed_previewed_and_its_changes_read(http, service, tmp_path):
    (tmp_path / "project" / "src").mkdir(parents=True)
    (tmp_path / "project" / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "secret.txt").write_text("no")
    thread = await _handed(service, tmp_path / "project")
    base = f"/conversations/{thread}/agent/folder"

    listing = (await http.get(base)).json()
    assert [(e["name"], e["path"], e["folder"]) for e in listing["entries"]] == [("src", "src", True)]
    assert (await http.get(f"{base}/file", params={"path": "src/a.py"})).json()["text"] == "x = 1\n"
    assert (await http.get(f"{base}/changes")).json()["repository"] is False

    assert (await http.get(f"{base}/file", params={"path": "../secret.txt"})).status_code == 400
    assert (await http.get(base, params={"path": "/etc"})).status_code == 400
    assert (await http.get(f"{base}/file", params={"path": "gone.py"})).status_code == 404


async def test_a_conversation_not_handed_to_an_agent_has_no_folder(http, service):
    thread = await service.new_thread("owner")
    assert (await http.get(f"/conversations/{thread}/agent/folder")).status_code == 404


async def test_the_home_folder_is_listed_and_previewed_without_leaving_it(http, tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "notes").mkdir(parents=True)
    (home / "notes" / "todo.md").write_text("milk\n")
    (home / "node_modules").mkdir()
    (tmp_path / "secret.txt").write_text("no")
    (home / "out").symlink_to(tmp_path / "secret.txt")
    monkeypatch.setenv("HOME", str(home))

    listing = (await http.get("/folders/home")).json()
    assert [(e["name"], e["folder"]) for e in listing["entries"]] == [("notes", True)]
    assert (await http.get("/folders/home/file", params={"path": "notes/todo.md"})).json()["text"] == "milk\n"

    assert (await http.get("/folders/home/file", params={"path": "../secret.txt"})).status_code == 400
    assert (await http.get("/folders/home/file", params={"path": "out"})).status_code == 400
    assert (await http.get("/folders/home", params={"path": "/etc"})).status_code == 400
    assert (await http.get("/folders/home", params={"path": "node_modules"})).status_code == 400
    assert (await http.get("/folders/home/file", params={"path": "gone.md"})).status_code == 404


async def test_a_file_of_either_folder_is_deleted_but_not_a_folder_or_outside_it(
    http, service, tmp_path, monkeypatch, trashed
):
    (tmp_path / "project" / "src").mkdir(parents=True)
    (tmp_path / "project" / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "note.md").write_text("milk\n")
    (tmp_path / "secret.txt").write_text("no")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    handed = f"/conversations/{await _handed(service, tmp_path / 'project')}/agent/folder/file"
    assert (await http.put("/settings/folder-deleting", json={"enabled": True})).json() == {"enabled": True}

    assert (await http.delete(handed, params={"path": "src/a.py"})).status_code == 200
    assert (await http.delete("/folders/home/file", params={"path": "note.md"})).status_code == 200
    assert not (tmp_path / "project" / "src" / "a.py").exists() and not (tmp_path / "home" / "note.md").exists()
    assert {p.name for p in trashed.iterdir()} == {"a.py", "note.md"}  # in the trash, not gone for good

    assert (await http.delete(handed, params={"path": "src"})).status_code == 404
    assert (await http.delete("/folders/home/file", params={"path": "../secret.txt"})).status_code == 400
    assert (await http.delete("/folders/home/file", params={"path": "gone.md"})).status_code == 404
    assert (tmp_path / "project" / "src").is_dir() and (tmp_path / "secret.txt").exists()


async def test_deleting_is_refused_until_turned_on_and_again_once_turned_off(http, tmp_path, monkeypatch):
    (tmp_path / "note.md").write_text("milk\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert (await http.get("/settings/folder-deleting")).json() == {"enabled": False}
    assert (await http.delete("/folders/home/file", params={"path": "note.md"})).status_code == 403

    await http.put("/settings/folder-deleting", json={"enabled": True})
    await http.put("/settings/folder-deleting", json={"enabled": False})
    assert (await http.get("/settings/folder-deleting")).json() == {"enabled": False}
    assert (await http.delete("/folders/home/file", params={"path": "note.md"})).status_code == 403
    assert (tmp_path / "note.md").exists()


def _git(where, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=where, check=True, capture_output=True
    )


async def test_the_client_reads_the_handed_folder_its_changes_and_diffs(client, service, tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-gitconfig"))
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "a.py").write_text("x = 1\n")
    (project / "README.md").write_text("# P\n")
    _git(project, "init", "-q")
    _git(project, "add", ".")
    _git(project, "commit", "-qm", "start")
    (project / "README.md").unlink()
    (project / "src" / "a.py").write_text("x = 2\n")
    folder = client.folders.handed(await _handed(service, project))

    listing = await folder.contents()
    assert [(e.name, e.deleted) for e in listing.entries] == [("src", False), ("README.md", True)]
    changed = (await folder.refresh([""])).changes
    assert sorted((c.path, c.status) for c in changed.changes) == [
        ("README.md", "deleted"),
        ("src/a.py", "modified"),
    ]
    shown = await folder.diff("src/a.py")
    assert shown.text is not None and "-x = 1" in shown.text and "+x = 2" in shown.text
    assert (await folder.file("src/a.py")).text == "x = 2\n"
    with pytest.raises(MissingPathError):
        await folder.diff("README")
    with pytest.raises(HandedFolderError):
        await folder.file("../secret.txt")


async def test_the_client_moves_a_file_to_the_trash_once_deleting_is_on(client, tmp_path, monkeypatch, trashed):
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "note.md").write_text("milk\n")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    home = client.folders.home()
    assert not home.has_changes and not await client.folders.deleting()
    with pytest.raises(DeletingOffError):
        await home.delete("note.md")
    assert await client.folders.set_deleting(True)
    await home.delete("note.md")
    assert not (tmp_path / "home" / "note.md").exists() and (trashed / "note.md").read_text() == "milk\n"


async def test_a_refresh_reads_the_open_folders_and_the_changes_together(http, client, service, tmp_path):
    (tmp_path / "project" / "src").mkdir(parents=True)
    (tmp_path / "project" / "src" / "a.py").write_text("x = 1\n")
    thread = await _handed(service, tmp_path / "project")
    base = f"/conversations/{thread}/agent/folder/refresh"
    found = (await http.get(base, params={"path": ["", "src", "gone"]})).json()
    assert [(f["path"], bool(f["contents"]), bool(f["error"])) for f in found["folders"]] == [
        ("", True, False),
        ("src", True, False),
        ("gone", False, True),
    ]
    assert found["changes"]["repository"] is False
    read = await client.folders.handed(thread).refresh(["", "src"])
    assert [f.path for f in read.folders] == ["", "src"] and read.folders[1].contents is not None
    assert [e.name for e in read.folders[1].contents.entries] == ["a.py"] and not read.changes.repository
    other = await service.new_thread("owner")
    assert (await http.get(f"/conversations/{other}/agent/folder/refresh", params={"path": ""})).status_code == 404
