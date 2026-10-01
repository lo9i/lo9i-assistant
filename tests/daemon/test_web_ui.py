"""The web UI at /app/, and the checks that keep other sites' pages away from the localhost port."""

import asyncio
import tempfile
from pathlib import Path

import httpx
import uvicorn

from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER


def _http(app, host: str = "127.0.0.1", **headers: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"http://{host}:8765", headers=headers)


async def test_the_built_page_is_served_without_the_client_header(service, tmp_path):
    (tmp_path / "index.html").write_text("<title>lo9i</title>")
    async with _http(create_app(service, RunHub(), web_ui=tmp_path)) as http:
        response = await http.get("/app", follow_redirects=True)
        assert response.status_code == 200 and "lo9i" in response.text
        assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
        assert (await http.get("/conversations")).status_code == 403


async def test_the_pages_own_routes_are_answered_with_the_page(service, tmp_path):
    (tmp_path / "index.html").write_text("<title>lo9i</title>")
    (tmp_path / "app.js").write_text("console.log(1)")
    async with _http(create_app(service, RunHub(), web_ui=tmp_path)) as http:
        assert "lo9i" in (await http.get("/app/jobs")).text
        assert "lo9i" in (await http.get("/app/settings?tab=usage")).text
        assert (await http.get("/app/app.js")).text == "console.log(1)"


async def test_an_unbuilt_page_says_how_to_build_it(service, tmp_path):
    async with _http(create_app(service, RunHub(), web_ui=tmp_path / "missing")) as http:
        response = await http.get("/app/")
        assert response.status_code == 404 and "isn't built" in response.text


async def test_requests_naming_another_host_are_refused(service):
    app = create_app(service, RunHub())
    async with _http(app, "rebound.example", **{CLIENT_HEADER: "web"}) as http:
        assert (await http.get("/conversations")).status_code == 403
    async with _http(app, "localhost", **{CLIENT_HEADER: "web"}) as http:
        assert (await http.get("/conversations")).status_code == 401  # A known host, but not paired.


async def test_unix_socket_requests_are_not_checked_for_the_host(service):
    # Short path: macOS limits Unix socket paths to 104 bytes.
    socket_path = Path(tempfile.mkdtemp(prefix="lo9i-")) / "d.sock"
    app = trusted(create_app(service, RunHub()))  # As the daemon serves its socket.
    server = uvicorn.Server(uvicorn.Config(app, uds=str(socket_path), lifespan="off"))
    task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        transport = httpx.AsyncHTTPTransport(uds=str(socket_path))
        async with httpx.AsyncClient(transport=transport, base_url="http://lo9i", headers={CLIENT_HEADER: "t"}) as http:
            assert (await http.get("/conversations")).status_code == 200
    finally:
        server.should_exit = True
        await task
        socket_path.unlink(missing_ok=True)
        socket_path.parent.rmdir()
