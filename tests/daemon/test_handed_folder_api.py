"""The handed folder's routes: read only while the conversation is with an agent, only inside its folder."""

import httpx
import pytest

from assistant.core.agent import Session
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
