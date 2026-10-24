"""The daemon's HTTP servers (daemon/http_server.py), serving its own app: requests and event streams over the Unix
socket, and a stop that doesn't wait on a stream left open."""

import asyncio
import tempfile
import time
from pathlib import Path

import httpx
from sse_starlette.sse import AppStatus

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
