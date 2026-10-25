"""The daemon's HTTP servers (daemon/http_server.py), serving its own app: requests and event streams over the Unix
socket, and a stop that doesn't wait on a stream left open."""

import asyncio
import socket
import tempfile
import time
from pathlib import Path

import httpx
import pytest
from sse_starlette.sse import AppStatus

from assistant.daemon import server
from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.http_server import GRACEFUL_SECONDS, HttpServer, Listener
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER


async def test_the_api_and_its_event_stream_over_the_socket_and_a_stop_that_ends_the_stream(service):
    # Short path: macOS limits Unix socket paths to 104 bytes.
    socket_path = Path(tempfile.mkdtemp(prefix="lo9i-")) / "d.sock"
    stop = asyncio.Event()
    task = asyncio.create_task(
        HttpServer(trusted(create_app(service, RunHub())), Listener(socket=str(socket_path))).serve(stop)
    )
    transport = httpx.AsyncHTTPTransport(uds=str(socket_path))
    try:
        while not socket_path.exists():
            await asyncio.sleep(0.01)
        async with httpx.AsyncClient(transport=transport, base_url="http://lo9i", headers={CLIENT_HEADER: "t"}) as http:
            assert (await http.get("/health")).status_code == 200
            async with http.stream("GET", "/events") as events:
                assert events.status_code == 200
                service.bus.publish("jobs")
                lines = events.aiter_lines()
                while "jobs" not in await anext(lines):
                    pass
                started = time.monotonic()
                AppStatus.should_exit = True  # As the daemon does when it stops (server.py).
                stop.set()
                await asyncio.wait_for(task, GRACEFUL_SECONDS)
        assert time.monotonic() - started < GRACEFUL_SECONDS
    finally:
        AppStatus.should_exit = False
        stop.set()
        await asyncio.gather(task, return_exceptions=True)
        socket_path.unlink(missing_ok=True)
        socket_path.parent.rmdir()


async def test_a_listener_is_bound_before_it_serves_and_one_whose_port_is_taken_says_so(service):
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen()
    port = taken.getsockname()[1]
    try:
        app = create_app(service, RunHub())
        with pytest.raises(OSError):
            HttpServer(app, Listener(host="127.0.0.1", port=port)).bind()
        free = HttpServer(app, Listener(host="127.0.0.1", port=0))
        busy = HttpServer(app, Listener(host="127.0.0.1", port=port))
        assert not server._bound([free, busy])
        assert free._sockets is None  # Let go of, since the daemon doesn't start.
    finally:
        taken.close()


async def test_a_bound_listener_serves_on_what_it_bound(service):
    socket_path = Path(tempfile.mkdtemp(prefix="lo9i-")) / "d.sock"
    http_server = HttpServer(trusted(create_app(service, RunHub())), Listener(socket=str(socket_path)))
    http_server.bind()
    assert socket_path.exists()
    stop = asyncio.Event()
    task = asyncio.create_task(http_server.serve(stop))
    transport = httpx.AsyncHTTPTransport(uds=str(socket_path))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://lo9i", headers={CLIENT_HEADER: "t"}) as http:
            assert (await http.get("/health")).status_code == 200
    finally:
        stop.set()
        await task
        socket_path.unlink(missing_ok=True)
        socket_path.parent.rmdir()
