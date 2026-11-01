"""OpenAI's Realtime API, as live voice calls use it: a call made over WebRTC from the browser's offer, the sideband
WebSocket the daemon keeps on it, hanging up, and checking a key. Audio never comes here: the browser and OpenAI
exchange it directly; only the offer, the answer and the call's events do.

https://developers.openai.com/api/docs/guides/voice-webrtc (the unified interface: the server posts the offer with the
call's settings to /v1/realtime/calls and gets the answer, the call's id in its Location header) and
https://developers.openai.com/api/docs/guides/voice-server-controls (the sideband: wss://…/v1/realtime?call_id=)."""

import json
from collections.abc import AsyncIterator, Awaitable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK, InvalidHandshake

from assistant.core.i18n import said
from assistant.core.llm.connections import transport

API = "https://api.openai.com/v1"
SIDEBAND = "wss://api.openai.com/v1/realtime"
# The speech-to-speech model the calls use.
MODEL = "gpt-realtime-2.1"
_TIMEOUT = httpx.Timeout(30)
# A call's events are small (no audio comes to the sideband of a WebRTC call), but a long tool result can be large.
_MAX_EVENT_BYTES = 16 * 1024 * 1024
# Characters of an error's body kept when it isn't the API's JSON.
_ERROR_CHARS = 300


class RealtimeError(Exception):
    """OpenAI refused, or couldn't be reached. Its message says why, for the user."""


class SidebandLostError(RealtimeError):
    """The sideband closed without the call ending: it can be opened again on the same call."""


@dataclass(frozen=True)
class Answer:
    """What the browser completes its peer connection with, and the call's id."""

    call_id: str
    sdp: str


class Sideband(Protocol):
    """The daemon's connection to a call: the call's events, and commands to it."""

    async def send(self, event: dict[str, Any]) -> None: ...

    def events(self) -> AsyncIterator[dict[str, Any]]:
        """Until the call ends. Raises SidebandLostError when the connection drops before."""
        ...


class Realtime(Protocol):
    """What the service and the daemon use of the Realtime API; the tests fake it."""

    async def check_key(self, key: str) -> None:
        """Raises RealtimeError unless the key can use the model."""
        ...

    async def call(self, key: str, offer: str, session: dict[str, Any]) -> Answer:
        """Starts a call from the browser's SDP offer. Raises RealtimeError."""
        ...

    async def hang_up(self, key: str, call_id: str) -> None:
        """Ends the call; one that ended already is no error. Raises RealtimeError."""
        ...

    def sideband(self, key: str, call_id: str) -> AbstractAsyncContextManager[Sideband]:
        """Opens the call's sideband. Raises RealtimeError when it can't."""
        ...


class OpenAIRealtime:
    def __init__(self, http: httpx.AsyncBaseTransport | None = None) -> None:
        """`http`: the tests' transport; else one that notices a connection that died (core/llm/connections.py)."""
        self._http = http

    async def check_key(self, key: str) -> None:
        async with self._client(key) as client:
            response = await _requested(client.get(f"/models/{MODEL}"))
        _raise_for(response)

    async def call(self, key: str, offer: str, session: dict[str, Any]) -> Answer:
        parts = {"sdp": (None, offer, "application/sdp"), "session": (None, json.dumps(session), "application/json")}
        async with self._client(key) as client:
            response = await _requested(client.post("/realtime/calls", files=parts))
        _raise_for(response)
        call_id = response.headers.get("location", "").rstrip("/").rsplit("/", 1)[-1]
        if not call_id:
            raise RealtimeError(said("OpenAI answered the call without its id."))
        return Answer(call_id, response.text)

    async def hang_up(self, key: str, call_id: str) -> None:
        async with self._client(key) as client:
            response = await _requested(client.post(f"/realtime/calls/{call_id}/hangup"))
        if response.status_code != 404:
            _raise_for(response)

    @asynccontextmanager
    async def sideband(self, key: str, call_id: str) -> AsyncIterator[Sideband]:
        url = f"{SIDEBAND}?{urlencode({'call_id': call_id})}"
        try:
            headers = {"Authorization": f"Bearer {key}"}
            socket = await connect(url, additional_headers=headers, max_size=_MAX_EVENT_BYTES)
        except (InvalidHandshake, OSError, TimeoutError) as e:
            raise RealtimeError(said("Couldn't connect to the call: {error}", error=e)) from e
        try:
            yield _Socket(socket)
        finally:
            await socket.close()

    def _client(self, key: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=API,
            transport=self._http or transport(),
            timeout=_TIMEOUT,
            headers={"Authorization": f"Bearer {key}"},
        )


class _Socket:
    def __init__(self, socket: ClientConnection) -> None:
        self._socket = socket

    async def send(self, event: dict[str, Any]) -> None:
        try:
            await self._socket.send(json.dumps(event))
        except ConnectionClosedOK:
            return
        except ConnectionClosedError as e:
            raise SidebandLostError(said("The connection to the call dropped: {error}", error=e)) from e

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        try:
            async for raw in self._socket:
                yield json.loads(raw)
        except ConnectionClosedError as e:
            raise SidebandLostError(said("The connection to the call dropped: {error}", error=e)) from e


async def _requested(request: Awaitable[httpx.Response]) -> httpx.Response:
    try:
        return await request
    except httpx.HTTPError as e:
        raise RealtimeError(said("Couldn't reach OpenAI: {error}", error=e)) from e


def _raise_for(response: httpx.Response) -> None:
    if response.is_success:
        return
    raise RealtimeError(said("OpenAI refused: {error}", error=_error(response)))


def _error(response: httpx.Response) -> str:
    """The API's message, else the start of the body, else the status."""
    try:
        found = response.json().get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        found = ""
    return found or response.text[:_ERROR_CHARS].strip() or f"HTTP {response.status_code}"
