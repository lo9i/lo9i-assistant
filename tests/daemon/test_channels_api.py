"""The channel routes: what a channel plugin's process reaches with its token, and what the apps see."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

import httpx
import pytest
import uvicorn

from assistant.core.channels.chat.port import ChatLimits
from assistant.core.mcp import servers
from assistant.core.mcp.servers import McpServer
from assistant.daemon.api import create_app
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER


@pytest.fixture
async def app(service):
    await servers.save(service.store, McpServer("telegram", channel_command="uv", channel_protocol=2))
    await servers.save(service.store, McpServer("slack", command="uv", channel_command="uv", channel_protocol=2))
    return create_app(service, RunHub())


def _client(app, token: str = "") -> httpx.AsyncClient:
    headers = {CLIENT_HEADER: "channel"} | ({"Authorization": f"Bearer {token}"} if token else {})
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1", headers=headers)


async def test_a_channels_token_reaches_only_its_own_routes(app, service):
    token = service.channels_hub.issue_token("telegram")
    async with _client(app, token) as http:
        assert (await http.post("/channels/telegram/commands", json={"command": "start"})).status_code == 200
        assert (await http.post("/channels/slack/commands", json={"command": "start"})).status_code == 403
        assert (await http.get("/memory")).status_code == 403
        assert (await http.post("/channels/telegram/actions/x")).status_code == 403
    async with _client(app, "not-a-token") as http:
        assert (await http.post("/channels/telegram/commands", json={"command": "start"})).status_code == 401


async def test_a_device_cant_use_a_channels_routes(app, service):
    from assistant.daemon.auth import trusted

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=trusted(app)), base_url="http://127.0.0.1", headers={CLIENT_HEADER: "test"}
    ) as http:
        assert (await http.post("/channels/telegram/commands", json={"command": "start"})).status_code == 403
        listed = (await http.get("/channels")).json()
        assert [(c["name"], c["connected"]) for c in listed] == [("slack", False), ("telegram", False)]
        assert (await http.post("/channels/telegram/actions/new-pairing-code")).status_code == 409


async def test_a_channel_tells_the_apps_what_to_show(app, service):
    token = service.channels_hub.issue_token("telegram")
    items = [
        {"kind": "text", "label": "Bot: @lo9i_bot", "value": ""},
        {"kind": "qr", "label": "Scan", "value": "2@AbC,dEf"},
        {"kind": "action", "label": "New", "value": "n"},
    ]
    async with _client(app, token) as http:
        assert (await http.put("/channels/telegram/status", json={"items": items})).status_code == 200
        assert (await http.post("/channels/telegram/deliveries/unknown", json={"error": ""})).status_code == 200
        unknown = [{"kind": "image", "label": "", "value": "<svg/>"}]
        assert (await http.put("/channels/telegram/status", json={"items": unknown})).status_code == 422
    telegram = next(c for c in await service.channels() if c.name == "telegram")
    kinds = [(i.kind, i.label, i.value) for i in telegram.items]
    assert kinds == [("text", "Bot: @lo9i_bot", ""), ("qr", "Scan", "2@AbC,dEf"), ("action", "New", "n")]


async def test_new_sends_the_channels_next_message_to_a_new_conversation(app, service):
    token = service.channels_hub.issue_token("telegram")
    async with _client(app, token) as http:
        reply = await http.post("/channels/telegram/commands", json={"command": "clear"})
        assert reply.json() == {"text": "Your next message starts a new conversation."}
        assert await service.channel_takes_new("owner", "telegram")
        reply = await http.post("/channels/telegram/commands", json={"command": "home"})
        assert reply.json() == {"text": "Unknown command /home."}


async def test_a_channel_process_holds_its_stream_and_confirms_deliveries(app, service):
    """Over a real socket: the in-process transport doesn't stream."""
    token = service.channels_hub.issue_token("telegram")
    async with _serving(app) as base_url:
        headers = {CLIENT_HEADER: "channel", "Authorization": f"Bearer {token}"}
        http = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10)
        async with http, http.stream("GET", "/channels/telegram/stream?message_limit=2000&voice=true") as stream:
            lines = aiter(stream.aiter_lines())
            hello = {"assistant_name": await service.assistant_name(), "commands": await service.channel_commands()}
            assert await _next_event(lines) == ("hello", hello)
            assert service.channels_hub.limits("telegram") == ChatLimits(message_limit=2000, voice=True)
            sending = asyncio.create_task(service.outbox.send("telegram", "stretch"))
            kind, data = await _next_event(lines)
            assert (kind, data["chat"], data["text"]) == ("send", "", "stretch")
            await http.post(f"/channels/telegram/deliveries/{data['id']}", json={"error": "", "message": "7"})
            await sending
            assert service.channels_hub.connected("telegram")


async def test_a_message_answers_at_once_and_its_turn_reaches_the_chat_on_the_stream(app, service, script):
    token = service.channels_hub.issue_token("telegram")
    async with _serving(app) as base_url:
        headers = {CLIENT_HEADER: "channel", "Authorization": f"Bearer {token}"}
        http = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10)
        async with http, http.stream("GET", "/channels/telegram/stream?edit_seconds=0") as stream:
            lines = aiter(stream.aiter_lines())
            await _next_event(lines)
            files = [("files", ("note.txt", b"hi", "text/plain"))]
            sent = await http.post("/channels/telegram/messages", data={"chat": "42", "text": "hi"}, files=files)
            assert sent.status_code == 200
            kind, data = await _next_event(lines)
            assert (kind, data["chat"]) == ("typing", "42")
            await http.post(f"/channels/telegram/deliveries/{data['id']}", json={})
            session = await service.session("owner", "telegram")
            for _ in range(200):
                if len(await service.conversation_messages(session.thread_id)) == 2:
                    break
                await asyncio.sleep(0.02)
            assert (await service.conversation_messages(session.thread_id))[0].text.endswith("hi")


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
