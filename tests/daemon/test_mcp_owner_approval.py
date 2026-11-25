"""A paired device's local MCP server (a command run on this computer) waits for the owner's approval on a chat channel
before it's probed, saved or given a new command; the Unix socket and remote servers don't ask."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from lo9i.core.mcp import servers
from lo9i.daemon.api import create_app
from lo9i.daemon.auth import trusted
from lo9i.daemon.runs import RunHub
from lo9i.protocol import CLIENT_HEADER

_LOCAL = {"name": "evil", "command": "sh", "args": ["-c", "touch /tmp/owned"]}


class _Owner:
    """A chat channel where the owner answers every request as told."""

    def __init__(self, service, approved: bool) -> None:
        self._service, self._approved = service, approved
        self.asked: list[dict[str, Any]] = []

    async def forward(self, interrupt_id: str, title: str, request: dict[str, Any]) -> None:
        self.asked.append(request)
        self._service.approvals.answer(interrupt_id, {"approved": self._approved})


@pytest.fixture
def app(service):
    return create_app(service, RunHub())


def _socket(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=trusted(app))
    return httpx.AsyncClient(transport=transport, base_url="http://lo9i", headers={CLIENT_HEADER: "cli"})


@asynccontextmanager
async def _device(app) -> AsyncIterator[httpx.AsyncClient]:
    """A browser paired over the network."""
    transport = httpx.ASGITransport(app=app, client=("203.0.113.7", 51000))
    async with _socket(app) as cli:
        code = (await cli.post("/devices/pairing")).json()["code"]
    headers = {CLIENT_HEADER: "web"}
    async with httpx.AsyncClient(transport=transport, base_url="https://localhost", headers=headers) as browser:
        assert (await browser.post("/auth/pair", json={"code": code, "name": "Laptop"})).status_code == 200
        yield browser


async def _saved(service) -> list[str]:
    return [s.name for s in await servers.load_all(service._storage.store)]


async def test_a_device_cant_add_a_local_server_with_no_channel_to_ask_the_owner(app, service):
    async with _device(app) as browser:
        assert (await browser.post("/mcp/servers", json=_LOCAL)).status_code == 403
        assert (await browser.post("/mcp/probe", json=_LOCAL)).status_code == 403
    assert await _saved(service) == []


async def test_a_local_server_the_owner_rejects_isnt_saved(app, service):
    owner = _Owner(service, approved=False)
    service.approvals.register("telegram", owner)
    async with _device(app) as browser:
        assert (await browser.post("/mcp/servers", json=_LOCAL)).status_code == 403
    assert await _saved(service) == []
    assert "touch /tmp/owned" in owner.asked[0]["command"] and "Laptop" in owner.asked[0]["reason"]


async def test_a_local_server_the_owner_approves_is_saved(app, service):
    service.approvals.register("telegram", _Owner(service, approved=True))
    async with _device(app) as browser:
        assert (await browser.post("/mcp/servers", json={**_LOCAL, "enabled": False})).status_code == 200
    assert await _saved(service) == ["evil"]


async def test_a_device_giving_a_server_a_new_command_asks_the_owner(app, service):
    async with _socket(app) as cli:
        assert (await cli.post("/mcp/servers", json={**_LOCAL, "enabled": False})).status_code == 200
    owner = _Owner(service, approved=False)
    service.approvals.register("telegram", owner)
    async with _device(app) as browser:
        assert (await browser.patch("/mcp/servers/evil", json={"trusted": True})).status_code == 200
        assert (await browser.patch("/mcp/servers/evil", json={"args": ["-c", "rm -rf ~"]})).status_code == 403
    assert len(owner.asked) == 1
    assert (await servers.load(service._storage.store, "evil")).args == _LOCAL["args"]


async def test_a_remote_server_from_a_device_doesnt_ask(app, service):
    remote = {"name": "docs", "url": "https://mcp.example.com/mcp", "enabled": False}
    async with _device(app) as browser:
        assert (await browser.post("/mcp/servers", json=remote)).status_code == 200
    assert await _saved(service) == ["docs"]


async def test_a_device_changing_env_asks_only_for_variables_that_change_what_runs(app, service):
    async with _socket(app) as cli:
        assert (await cli.post("/mcp/servers", json={**_LOCAL, "enabled": False})).status_code == 200
    owner = _Owner(service, approved=False)
    service.approvals.register("telegram", owner)
    async with _device(app) as browser:
        assert (await browser.patch("/mcp/servers/evil", json={"env": {"API_TOKEN": "t0ken"}})).status_code == 200
        preload = {"API_TOKEN": "t0ken", "DYLD_INSERT_LIBRARIES": "/tmp/x.dylib"}
        assert (await browser.patch("/mcp/servers/evil", json={"env": preload})).status_code == 403
        assert (await browser.patch("/mcp/servers/evil", json={"env": {"NODE_OPTIONS": "-r x"}})).status_code == 403
    asked = [a["command"] for a in owner.asked]
    assert len(asked) == 2 and "DYLD_INSERT_LIBRARIES=/tmp/x.dylib" in asked[0] and "NODE_OPTIONS" in asked[1]
    assert "t0ken" not in asked[0]
    assert "DYLD_INSERT_LIBRARIES" not in (await servers.load(service._storage.store, "evil")).env


async def test_a_device_adding_a_repository_asks_the_owner(app, service):
    async with _device(app) as browser:
        response = await browser.post("/repositories", json={"url": "https://github.com/me/plugins.git"})
    assert response.status_code == 403
