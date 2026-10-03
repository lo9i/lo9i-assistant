"""The adapter follows the stored tokens: it connects, reconnects on a change, disconnects when they're
removed, and acknowledges every Slack request before working on it."""

import asyncio
from typing import ClassVar

import pytest
from slack_sdk.errors import SlackClientError
from slack_sdk.socket_mode.request import SocketModeRequest

import assistant.gateways.slack.bot as bot
from assistant.core.integrations import slack


class _Socket:
    instances: ClassVar[list["_Socket"]] = []

    def __init__(self, app_token, web_client):
        self.app_token = app_token
        self.socket_mode_request_listeners = []
        self.responses = []
        self.closed = False
        _Socket.instances.append(self)

    async def connect(self):
        if self.app_token == "xapp-down":
            raise SlackClientError("down")

    async def close(self):
        self.closed = True

    async def send_socket_mode_response(self, response):
        self.responses.append(response)


@pytest.fixture(autouse=True)
def fake_socket(monkeypatch):
    _Socket.instances = []
    monkeypatch.setattr(bot, "SocketModeClient", _Socket)


def _config(app_token="xapp-1"):
    return slack.SlackConfig(app_token, "xoxb-1", "xoxp-1", "Acme", "U1", "ani")


async def _until(condition):
    for _ in range(200):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met")


async def test_follows_the_stored_tokens(service):
    stop = asyncio.Event()
    run = asyncio.create_task(bot.SlackAdapter(service).run(stop))
    await slack.save(service.store, _config())
    await _until(lambda: "slack" in service.outbox.channels)
    await slack.save(service.store, _config("xapp-2"))
    await _until(lambda: len(_Socket.instances) == 2 and "slack" in service.outbox.channels)
    assert _Socket.instances[0].closed and _Socket.instances[1].app_token == "xapp-2"
    await slack.clear(service.store)
    await _until(lambda: "slack" not in service.outbox.channels)
    stop.set()
    await run


async def test_a_connection_that_cant_open_fails_the_adapter(service):
    await slack.save(service.store, _config("xapp-down"))
    with pytest.raises(SlackClientError):
        await bot.SlackAdapter(service).run(asyncio.Event())
    assert "slack" not in service.outbox.channels


async def test_requests_are_acknowledged_and_retries_skipped(service):
    stop = asyncio.Event()
    await slack.save(service.store, _config())
    run = asyncio.create_task(bot.SlackAdapter(service).run(stop))
    await _until(lambda: "slack" in service.outbox.channels)
    socket = _Socket.instances[0]
    listener = socket.socket_mode_request_listeners[0]
    await listener(socket, SocketModeRequest("slash_commands", "e1", {"user_id": "U1", "command": "/new"}))
    assert socket.responses[0].payload == {"text": "Started a new conversation."}
    retry = SocketModeRequest("events_api", "e2", {"event": {"type": "message"}}, retry_attempt=1)
    await listener(socket, retry)
    assert socket.responses[1].envelope_id == "e2"
    stop.set()
    await run
