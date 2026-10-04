"""The channel routes: what a channel plugin's process reaches with its token, and what the apps see."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

import httpx
import pytest
import uvicorn

from assistant.core.mcp import servers
from assistant.core.mcp.servers import McpServer
from assistant.daemon.api import create_app
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER


@pytest.fixture
async def app(service):
    await servers.save(service.store, McpServer("telegram", channel_command="uv"))
    await servers.save(service.store, McpServer("slack", command="uv", channel_command="uv"))
    return create_app(service, RunHub())


def _client(app, token: str = "") -> httpx.AsyncClient:
    headers = {CLIENT_HEADER: "channel"} | ({"Authorization": f"Bearer {token}"} if token else {})
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1", headers=headers)


async def test_a_channels_token_reaches_only_its_own_routes(app, service):
    token = service.channels_hub.issue_token("telegram")
    async with _client(app, token) as http:
        assert (await http.get("/channels/telegram/approvals")).status_code == 200
        assert (await http.get("/channels/slack/approvals")).status_code == 403
        assert (await http.get("/memory")).status_code == 403
        assert (await http.post("/channels/telegram/actions/x")).status_code == 403
    async with _client(app, "not-a-token") as http:
        assert (await http.get("/channels/telegram/approvals")).status_code == 401


async def test_a_device_cant_use_a_channels_routes(app, service):
    from assistant.daemon.auth import trusted

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=trusted(app)), base_url="http://127.0.0.1", headers={CLIENT_HEADER: "test"}
    ) as http:
        assert (await http.get("/channels/telegram/approvals")).status_code == 403
        listed = (await http.get("/channels")).json()
        assert [(c["name"], c["connected"]) for c in listed] == [("slack", False), ("telegram", False)]
        assert (await http.post("/channels/telegram/actions/new-pairing-code")).status_code == 409


async def test_a_channel_tells_the_apps_what_to_show(app, service):
    token = service.channels_hub.issue_token("telegram")
    items = [{"kind": "text", "label": "Bot: @lo9i_bot", "value": ""}, {"kind": "action", "label": "New", "value": "n"}]
    async with _client(app, token) as http:
        assert (await http.put("/channels/telegram/status", json={"items": items})).status_code == 200
        assert (await http.post("/channels/telegram/deliveries/unknown", json={"error": ""})).status_code == 200
    telegram = next(c for c in await service.channels() if c.name == "telegram")
    assert [(i.kind, i.label) for i in telegram.items] == [("text", "Bot: @lo9i_bot"), ("action", "New")]


async def test_a_channel_chats_in_its_own_conversation(app, service, script):
    script.reply("Hello")
    token = service.channels_hub.issue_token("telegram")
    async with _client(app, token) as http:
        files = [("files", ("note.txt", b"hi", "text/plain"))]
        run = (await http.post("/channels/telegram/messages", data={"text": "hi"}, files=files)).json()
        events = await _run_events(http, f"/channels/telegram/runs/{run['run_id']}/events")
        assert events[-1]["type"] == "Done"
        assert (await http.get("/channels/telegram/approvals")).json() == []
        session = await service.session("owner", "telegram")
        created = (await http.post("/channels/telegram/conversation")).json()
        assert created["thread_id"] != session.thread_id
        assert (await service.session("owner", "telegram")).thread_id == created["thread_id"]
    async with _client(app, service.channels_hub.issue_token("slack")) as http:
        response = await http.get(f"/channels/slack/runs/{run['run_id']}/events")
        assert response.status_code == 404  # another channel's run


async def test_job_approvals_and_speech(app, service):
    token = service.channels_hub.issue_token("telegram")
    async with _client(app, token) as http:
        answer = await http.post("/channels/telegram/job-approvals/i1", json={"approved": True})
        assert answer.json() == {"waiting": False}
        spoken = await http.post("/channels/telegram/speech", json={"text": "hi", "after_voice_message": False})
        assert spoken.status_code == 204  # replies aren't spoken by default


async def test_a_channel_process_holds_its_stream_and_confirms_deliveries(app, service):
    """Over a real socket: the in-process transport doesn't stream."""
    token = service.channels_hub.issue_token("telegram")
    async with _serving(app) as base_url:
        headers = {CLIENT_HEADER: "channel", "Authorization": f"Bearer {token}"}
        http = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10)
        async with http, http.stream("GET", "/channels/telegram/stream") as stream:
            lines = aiter(stream.aiter_lines())
            assert await _next_event(lines) == ("hello", {"assistant_name": await service.assistant_name()})
            sending = asyncio.create_task(service.outbox.send("telegram", "stretch"))
            kind, data = await _next_event(lines)
            assert (kind, data["text"]) == ("deliver", "stretch")
            await http.post(f"/channels/telegram/deliveries/{data['id']}", json={"error": ""})
            await sending
            assert service.channels_hub.connected("telegram")


async def _run_events(http: httpx.AsyncClient, path: str) -> list[dict]:
    response = await http.get(path)
    data = [line.removeprefix("data: ") for line in response.text.splitlines() if line.startswith("data: ")]
    return [json.loads(d) for d in data if d != "{}"]


async def _next_event(lines: AsyncIterator[str]) -> tuple[str, dict]:
    kind = ""
    async for line in lines:
        if line.startswith("event: "):
            kind = line.removeprefix("event: ")
        elif line.startswith("data: ") and kind:
            return kind, json.loads(line.removeprefix("data: "))
    raise AssertionError("the stream ended")


@contextlib.asynccontextmanager
async def _serving(app) -> AsyncIterator[str]:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task
