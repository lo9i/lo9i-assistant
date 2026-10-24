"""MCP servers' web pages: run as their own process on a Unix socket, shown only to paired devices
through the daemon's pages port. The page here is a real process."""

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

import httpx
import pytest
from starlette.types import Message, Scope

from assistant.core.agent import McpServer, McpServerChanges
from assistant.core.mcp import folders
from assistant.daemon.auth import COOKIE
from assistant.daemon.pages import create_pages_app

# Answers every request with what it received, and tries to set a cookie the daemon must drop.
_PAGE = """
import json, sys
import uvicorn

async def app(scope, receive, send):
    if scope["type"] != "http":
        return
    if scope["path"] == "/late":
        await __import__("asyncio").sleep(2)
    if scope["path"] == "/stream":
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/event-stream")]})
        await send({"type": "http.response.body", "body": b"data: one\\n\\n", "more_body": True})
        await __import__("asyncio").sleep(1)
        await send({"type": "http.response.body", "body": b"data: two\\n\\n"})
        return
    seen = {"path": scope["path"], "query": scope["query_string"].decode(), "pid": __import__("os").getpid(),
            "headers": {k.decode(): v.decode() for k, v in scope["headers"]}}
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json"), (b"set-cookie", b"lo9i_device=planted")]})
    await send({"type": "http.response.body", "body": json.dumps(seen).encode()})
    if scope["path"] == "/quit":
        __import__("os")._exit(3)

uvicorn.run(app, uds=sys.argv[1], log_level="warning")
"""


@pytest.fixture
def short_data_dir(monkeypatch):
    # Under /tmp: macOS limits socket paths to 104 characters, and pytest's tmp_path is longer.
    folder = tempfile.mkdtemp(dir="/tmp")
    monkeypatch.setattr("assistant.core.config.settings.mcp_data_dir", folder)
    yield Path(folder)
    shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture
async def pages(service, short_data_dir, tmp_path):
    script = tmp_path / "page.py"
    script.write_text(_PAGE)
    page_args = [str(script), str(folders.page_socket("notes"))]
    await service.add_mcp_server(McpServer("notes", command="unused", page_command=sys.executable, page_args=page_args))
    stop = asyncio.Event()
    task = asyncio.create_task(service.pages.run(stop))
    await _until(lambda: folders.page_socket("notes").exists())
    yield service
    stop.set()
    await task


async def _until(condition, seconds: float = 15) -> None:
    async with asyncio.timeout(seconds):
        while not condition():
            await asyncio.sleep(0.05)


async def _paired(service) -> str:
    code = await service.open_device_pairing()
    _, token = await service.pair_device(code.code, "phone", "100.64.0.2")
    return token


def _http(service, token: str = "") -> httpx.AsyncClient:
    cookies = {COOKIE: token} if token else {}
    transport = httpx.ASGITransport(app=create_pages_app(service), client=("100.64.0.2", 5000))
    return httpx.AsyncClient(transport=transport, base_url="http://board:8766", cookies=cookies)


async def test_a_paired_device_sees_the_page_under_its_prefix_without_the_daemons_cookie(pages):
    async with _http(pages, await _paired(pages)) as http:
        answer = await http.get("/notes/bills/2?status=paid", headers={"X-Forwarded-Prefix": "/evil"})
    seen = answer.json()
    assert (seen["path"], seen["query"]) == ("/bills/2", "status=paid")
    assert seen["headers"]["x-forwarded-prefix"] == "/notes"
    assert "cookie" not in seen["headers"]
    assert "set-cookie" not in answer.headers
    assert answer.headers["content-security-policy"].startswith("frame-ancestors http://127.0.0.1:")


async def test_a_browser_that_leaves_before_sending_its_request_is_let_go_quietly(pages, caplog):
    token = await _paired(pages)
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/notes/save", "raw_path": b"/notes/save", "query_string": b"", "root_path": "",
        "headers": [(b"host", b"board:8766"), (b"cookie", f"{COOKIE}={token}".encode())],
        "client": ("100.64.0.2", 5000), "server": ("board", 8766),
    }  # fmt: skip
    await create_pages_app(pages)(scope, receive, send)
    assert sent[0]["status"] == 499
    assert "Traceback" not in caplog.text


async def test_a_page_streams_for_as_long_as_it_writes_once_it_started_in_time(pages, monkeypatch):
    from assistant.daemon import pages as page_proxy

    monkeypatch.setattr(page_proxy, "FIRST_BYTE_SECONDS", 0.5)
    async with _http(pages, await _paired(pages)) as http:
        streamed = await http.get("/notes/stream")
        late = await http.get("/notes/late")
    # Its second event came a second after the first, past the time a page has to start answering.
    assert (streamed.status_code, streamed.text) == (200, "data: one\n\ndata: two\n\n")
    assert streamed.headers["content-type"] == "text/event-stream"
    assert streamed.headers["content-security-policy"].startswith("frame-ancestors ")
    assert (late.status_code, late.text) == (504, "The page of notes didn't answer in time.")


async def test_pages_need_a_paired_device(pages):
    async with _http(pages) as http:
        assert (await http.get("/notes/")).status_code == 401
    async with _http(pages, "not-a-token") as http:
        assert (await http.get("/notes/")).status_code == 401


async def test_unknown_or_turned_off_pages_are_not_found(pages):
    token = await _paired(pages)
    async with _http(pages, token) as http:
        assert (await http.get("/other/")).status_code == 404
        assert (await http.get("/notes", follow_redirects=False)).headers["location"] == "/notes/"
        await pages.update_mcp_server("notes", McpServerChanges(enabled=False))
        assert (await http.get("/notes/")).status_code == 404
    await _until(lambda: not folders.page_socket("notes").exists())


async def test_a_page_that_exits_is_started_again(pages, monkeypatch):
    monkeypatch.setattr("assistant.core.mcp.process._FIRST_RETRY_SECONDS", 0.1)
    socket = folders.page_socket("notes")
    async with _http(pages, await _paired(pages)) as http:
        await http.get("/notes/quit")
        await _until(lambda: not socket.exists())
        await _until(socket.exists)
        assert (await http.get("/notes/again")).json()["path"] == "/again"


async def test_the_page_runs_with_the_servers_env(service, short_data_dir, tmp_path):
    script = tmp_path / "env_page.py"
    script.write_text(
        _PAGE.replace('"query": scope["query_string"].decode(),', '"env": __import__("os").environ.get("NOTES_DB"),')
    )
    socket = folders.page_socket("notes")
    await service.add_mcp_server(
        McpServer(
            "notes",
            command="unused",
            env={"NOTES_DB": "/data/notes.db"},
            page_command=sys.executable,
            page_args=[str(script), str(socket)],
        )
    )
    stop = asyncio.Event()
    task = asyncio.create_task(service.pages.run(stop))
    await _until(socket.exists)
    async with _http(service, await _paired(service)) as http:
        assert json.loads((await http.get("/notes/")).text)["env"] == "/data/notes.db"
    stop.set()
    await task


async def test_an_updated_page_runs_again_though_its_command_is_the_same(pages):
    async with _http(pages, await _paired(pages)) as http:
        before = (await http.get("/notes/")).json()["pid"]
        await pages.pages.restart("notes")
        await _until(lambda: folders.page_socket("notes").exists())
        await _until_answers(http)
        assert (await http.get("/notes/")).json()["pid"] != before


async def _until_answers(http) -> None:
    async with asyncio.timeout(15):
        while (await http.get("/notes/")).status_code != 200:
            await asyncio.sleep(0.05)


async def test_a_client_paired_for_a_token_reaches_the_page_with_it_as_a_bearer(pages):
    device, token = await pages.pair_device((await pages.open_device_pairing()).code, "Watchlist extension", "")
    transport = httpx.ASGITransport(app=create_pages_app(pages), client=("127.0.0.1", 5000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8766") as http:
        seen = (await http.get("/notes/x", headers={"Authorization": f"Bearer {token}"})).json()
        assert seen["path"] == "/x" and "authorization" not in seen["headers"]
        assert (await http.get("/notes/x", headers={"Authorization": "Bearer wrong"})).status_code == 401
    assert device.name == "Watchlist extension"
