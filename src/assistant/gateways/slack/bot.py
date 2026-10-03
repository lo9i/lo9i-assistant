"""The Slack adapter: keeps a Socket Mode connection open inside the daemon, so Slack needs no public
URL to reach it. The tokens come from the database (set from /slack); the adapter reconnects when
they change and disconnects when they're removed. Once connected, Slack's client reconnects by
itself; a connection that can't be opened fails the adapter, and the supervisor retries it."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Coroutine
from typing import Any

from slack_sdk.errors import SlackApiError, SlackClientError
from slack_sdk.socket_mode.async_client import AsyncBaseSocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.socket_mode.websockets import SocketModeClient
from slack_sdk.web.async_client import AsyncWebClient

from assistant.core.agent import AssistantService
from assistant.core.bus import BusEvent
from assistant.gateways.slack.handlers import Handlers
from assistant.gateways.slack.sender import SlackSender

logger = logging.getLogger(__name__)

_CHANNEL = "slack"


class SlackAdapter:
    """Keeps the Slack connection in sync with the tokens stored in the database."""

    name = "slack"

    def __init__(self, service: AssistantService) -> None:
        self._service = service

    async def run(self, stop: asyncio.Event) -> None:
        connection = _Connection(self._service)
        # Subscribed before the first sync, so a change made while it runs isn't missed.
        follow = asyncio.create_task(self._follow(self._service.bus.subscribe(self._service.bus.last_id), connection))
        stopped = asyncio.create_task(stop.wait())
        try:
            await connection.sync()
            await asyncio.wait({follow, stopped}, return_when=asyncio.FIRST_COMPLETED)
            if follow.done():
                follow.result()
        finally:
            follow.cancel()
            stopped.cancel()
            await connection.close()

    @staticmethod
    async def _follow(events: AsyncIterator[BusEvent], connection: "_Connection") -> None:
        async for event in events:
            if event.kind == "integrations":
                await connection.sync()


class _Connection:
    """One Socket Mode connection for the tokens currently stored, and the turns it started."""

    def __init__(self, service: AssistantService) -> None:
        self._service = service
        self._tokens: tuple[str, ...] = ()
        self._socket: SocketModeClient | None = None
        self._handlers: Handlers | None = None
        self._tasks: set[asyncio.Task] = set()

    async def sync(self) -> None:
        """Connects, reconnects or disconnects to match the stored tokens. Raises when Slack refuses
        the connection or can't be reached."""
        config = await self._service.slack_config()
        tokens = (config.app_token, config.bot_token, config.user_token, config.owner_id) if config.connected else ()
        if tokens == self._tokens:
            return
        await self.close()
        self._tokens = tokens
        if tokens:
            await self._open(config.app_token, config.bot_token, config.owner_id)

    async def close(self) -> None:
        if self._socket is None:
            return
        self._service.outbox.unregister(_CHANNEL)
        for task in self._tasks:
            task.cancel()
        with contextlib.suppress(SlackClientError, OSError):
            await self._socket.close()
        self._socket = self._handlers = None
        self._service.bus.publish("integrations")
        logger.info("Slack disconnected.")

    async def _open(self, app_token: str, bot_token: str, owner_id: str) -> None:
        web = AsyncWebClient(bot_token)
        socket = SocketModeClient(app_token, web_client=web)
        socket.socket_mode_request_listeners.append(self._on_request)
        try:
            await socket.connect()
        except (SlackApiError, SlackClientError, OSError):
            self._tokens = ()
            await socket.close()
            raise
        self._socket, self._handlers = socket, Handlers(self._service, web, bot_token, owner_id)
        self._service.outbox.register(_CHANNEL, SlackSender(web, owner_id))
        self._service.bus.publish("integrations")
        logger.info("Slack connected.")

    async def _on_request(self, client: AsyncBaseSocketModeClient, request: SocketModeRequest) -> None:
        """Every request is acknowledged right away (Slack resends after 3 seconds); the work runs after."""
        if self._handlers is None:
            return
        if request.type == "slash_commands":
            reply = await self._handlers.command(request.payload)
            await client.send_socket_mode_response(SocketModeResponse(request.envelope_id, payload=reply))
            return
        await client.send_socket_mode_response(SocketModeResponse(request.envelope_id))
        if request.retry_attempt:
            return
        if request.type == "events_api":
            self._spawn(self._handlers.message(request.payload.get("event", {})))
        elif request.type == "interactive":
            self._spawn(self._handlers.approval(request.payload))

    def _spawn(self, work: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(_logged(work))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


async def _logged(work: Coroutine[Any, Any, None]) -> None:
    try:
        await work
    except Exception:
        logger.exception("Slack request failed")
