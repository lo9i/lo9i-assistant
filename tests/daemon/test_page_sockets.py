"""Live connections to MCP servers' pages: a WebSocket from a paired device's browser, passed through the
pages port to the page on its Unix socket and back, with no time limit. The page and the pages port here
are real servers."""

import asyncio
import contextlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import httpx
import pytest
import uvicorn
from websockets.asyncio.client import connect, unix_connect
from websockets.asyncio.connection import Connection
from websockets.exceptions import ConnectionClosed, InvalidStatus

from assistant.core.agent import McpServer
from assistant.core.config import settings
from assistant.core.mcp import folders
from assistant.daemon.auth import COOKIE, DeviceStreams
from assistant.daemon.pages import PORT_OFFSET, create_pages_app

# Says what it saw, echoes what it gets, and does what some messages ask. Writes how the browser left to
# the file in argv[2].
_PAGE = """
import asyncio, json, sys
import uvicorn

async def app(scope, receive, send):
    if scope["type"] != "websocket":
        return
    await receive()
    asked = scope.get("subprotocols") or []
    await send({"type": "websocket.accept", "subprotocol": asked[0] if asked else None})
    seen = {"path": scope["path"], "query": scope["query_string"].decode(),
            "headers": {k.decode(): v.decode() for k, v in scope["headers"]}}
    await send({"type": "websocket.send", "text": json.dumps(seen)})
    while True:
        message = await receive()
        if message["type"] == "websocket.disconnect":
            # Whole or not at all: the test reads it as soon as it exists.
            with open(sys.argv[2] + ".part", "w") as left:
                left.write(str(message.get("code")))
            __import__("os").replace(sys.argv[2] + ".part", sys.argv[2])
            return
        if message.get("text") == "close":
            await send({"type": "websocket.close", "code": 4321, "reason": "done"})
            return
        if message.get("text") == "later":
            await asyncio.sleep(0.5)
            await send({"type": "websocket.send", "text": "still here"})
        elif message.get("text") is not None:
            await send({"type": "websocket.send", "text": "echo:" + message["text"]})
        else:
            await send({"type": "websocket.send", "bytes": message["bytes"][::-1]})

uvicorn.run(app, uds=sys.argv[1], log_level="warning")
"""


class _Server(uvicorn.Server):
    @contextlib.contextmanager
    def capture_signals(self):
        yield


@pytest.fixture
def short_dir(monkeypatch):
    # Under /tmp: macOS limits socket paths to 104 characters, and pytest's tmp_path is longer.
    folder = Path(tempfile.mkdtemp(dir="/tmp"))
    monkeypatch.setattr("assistant.core.config.settings.mcp_data_dir", str(folder))
    yield folder
    shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture
async def page(service, short_dir, tmp_path):
    """The `notes` page running, and the file it writes how the browser left to."""
    script = tmp_path / "page.py"
    script.write_text(_PAGE)
    left = tmp_path / "left"
    args = [str(script), str(folders.page_socket("notes")), str(left)]
    await service.add_mcp_server(McpServer("notes", command="unused", page_command=sys.executable, page_args=args))
    stop = asyncio.Event()
    task = asyncio.create_task(service.pages.run(stop))
    await _until(lambda: folders.page_socket("notes").exists())
    yield left
    stop.set()
    await task


@pytest.fixture
def streams():
    return DeviceStreams()


@pytest.fixture
async def pages_port(service, short_dir, streams):
    """The pages port, served on a Unix socket."""
    path = str(short_dir / "pages.sock")
    server = _Server(uvicorn.Config(create_pages_app(service, streams), uds=path, log_level="warning", lifespan="off"))
    task = asyncio.create_task(server.serve())
    await _until(lambda: server.started)
    yield path
    server.should_exit = True
    await task


async def _until(condition, seconds: float = 15) -> None:
    async with asyncio.timeout(seconds):
        while not condition():
            await asyncio.sleep(0.05)


async def _paired(service) -> tuple[str, str]:
    code = await service.open_device_pairing()
    device, token = await service.pair_device(code.code, "phone", "100.64.0.2")
    return device.id, token


def _page_origin() -> str:
    return f"http://127.0.0.1:{settings.daemon_port + PORT_OFFSET}"


def _open(pages_port: str, path: str, token: str = "", origin: str | None = None, **kwargs) -> connect:
    headers = {"Cookie": f"{COOKIE}={token}"} if token else {}
    return unix_connect(pages_port, f"ws://127.0.0.1{path}", origin=origin, additional_headers=headers, **kwargs)


async def _seen(ws: Connection) -> dict:
    return json.loads(await ws.recv())


async def test_a_paired_device_talks_to_the_page_both_ways_under_its_prefix(service, page, pages_port):
    _, token = await _paired(service)
    async with _open(pages_port, "/notes/term/pi?cols=80", token, _page_origin(), subprotocols=["tty"]) as ws:
        seen = await _seen(ws)
        assert ws.subprotocol == "tty"
        await ws.send("hi")
        assert await ws.recv() == "echo:hi"
        await ws.send(b"\x00\x01\x02")
        assert await ws.recv() == b"\x02\x01\x00"
    assert (seen["path"], seen["query"]) == ("/term/pi", "cols=80")
    assert seen["headers"]["x-forwarded-prefix"] == "/notes"
    assert "cookie" not in seen["headers"] and "authorization" not in seen["headers"]


async def test_it_stays_open_past_the_time_a_request_gets(service, page, pages_port, monkeypatch):
    monkeypatch.setattr("assistant.daemon.pages._TIMEOUT", httpx.Timeout(0.1))
    _, token = await _paired(service)
    async with _open(pages_port, "/notes/", token, _page_origin()) as ws:
        await _seen(ws)
        await ws.send("later")
        assert await ws.recv() == "still here"


async def test_the_page_closing_closes_the_browser_the_same_way(service, page, pages_port):
    _, token = await _paired(service)
    async with _open(pages_port, "/notes/", token, _page_origin()) as ws:
        await _seen(ws)
        await ws.send("close")
        with pytest.raises(ConnectionClosed):
            await ws.recv()
    assert (ws.close_code, ws.close_reason) == (4321, "done")


async def test_the_browser_leaving_tells_the_page(service, page, pages_port):
    _, token = await _paired(service)
    async with _open(pages_port, "/notes/", token, _page_origin()) as ws:
        await _seen(ws)
    await _until(page.exists)
    assert page.read_text() == "1000"


async def test_revoking_the_device_closes_its_connections(service, page, pages_port, streams):
    device_id, token = await _paired(service)
    async with _open(pages_port, "/notes/", token, _page_origin()) as ws:
        await _seen(ws)
        streams.end(device_id)
        with pytest.raises(ConnectionClosed):
            await ws.recv()
    assert ws.close_code == 1008
    await _until(page.exists)


async def test_live_connections_need_a_paired_device(service, page, pages_port):
    for token in ("", "not-a-token"):
        with pytest.raises(InvalidStatus) as refused:
            await _open(pages_port, "/notes/", token, _page_origin())
        assert refused.value.response.status_code == 401


@pytest.mark.parametrize(
    "origin", ["http://evil.example", "http://127.0.0.1:3000", f"http://127.0.0.1:{settings.daemon_port}"]
)
async def test_only_the_pages_may_open_one_from_a_browser(service, page, pages_port, origin):
    _, token = await _paired(service)
    with pytest.raises(InvalidStatus) as refused:
        await _open(pages_port, "/notes/", token, origin)
    assert refused.value.response.status_code == 403


async def test_a_client_with_its_token_and_no_origin_connects(service, page, pages_port):
    _, token = await _paired(service)
    headers = {"Authorization": f"Bearer {token}"}
    async with unix_connect(pages_port, "ws://127.0.0.1/notes/x", additional_headers=headers) as ws:
        assert (await _seen(ws))["path"] == "/x"


async def test_a_server_without_a_running_page_is_not_found(service, page, pages_port):
    _, token = await _paired(service)
    with pytest.raises(InvalidStatus) as refused:
        await _open(pages_port, "/other/", token, _page_origin())
    assert refused.value.response.status_code == 404
