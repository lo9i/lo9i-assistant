"""DaemonClient: the service's gateway-facing methods, implemented over the daemon's HTTP API."""

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

import httpx

from assistant.client.launcher import socket_path, start_daemon, wait_until_ready
from assistant.client.sse import read_events
from assistant.core.agent import InvalidToken, MemorySnapshot, Session, TelegramStatus
from assistant.core.attachments import Attachment
from assistant.core.events import Event
from assistant.protocol import CLIENT_HEADER, END, event_from_dict

_BASE = "http://lo9i"
# Replies can take minutes; only connecting should be quick.
_TIMEOUT = httpx.Timeout(connect=5, read=None, write=60, pool=5)
_RECONNECTS = 5


class DaemonClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def session(self, user_id: str, channel: str) -> Session:
        return Session(**(await self._get(f"/sessions/{channel}")))

    async def new_thread(self, user_id: str) -> str:
        return (await self._post("/threads"))["thread_id"]

    async def memory_snapshot(self, user_id: str) -> MemorySnapshot:
        return MemorySnapshot(**(await self._get("/memory")))

    async def send(self, session: Session, text: str, attachments: Sequence[Attachment] = ()) -> AsyncIterator[Event]:
        files = [("files", (a.name, a.data, a.media_type)) for a in attachments]
        data = {"channel": session.channel, "text": text}
        run = await self._post(f"/threads/{session.thread_id}/messages", data=data, files=files or None)
        async for event in self._follow(run["run_id"]):
            yield event

    async def resume(self, session: Session, decisions: dict[str, dict[str, Any]]) -> AsyncIterator[Event]:
        body = {"channel": session.channel, "decisions": decisions}
        run = await self._post(f"/threads/{session.thread_id}/approvals", json=body)
        async for event in self._follow(run["run_id"]):
            yield event

    async def telegram_status(self) -> TelegramStatus:
        return TelegramStatus(**(await self._get("/integrations/telegram")))

    async def connect_telegram(self, token: str) -> TelegramStatus:
        response = await self._http.post("/integrations/telegram", json={"token": token})
        if response.status_code == 400:
            raise InvalidToken(response.json()["detail"])
        response.raise_for_status()
        return TelegramStatus(**response.json())

    async def start_telegram_pairing(self) -> TelegramStatus:
        return TelegramStatus(**(await self._post("/integrations/telegram/pairing")))

    async def disconnect_telegram(self) -> None:
        (await self._http.delete("/integrations/telegram")).raise_for_status()

    async def _follow(self, run_id: str) -> AsyncIterator[Event]:
        """Stream a run's events, reconnecting from the last event id if the connection drops."""
        last_id = "0"
        for _ in range(_RECONNECTS):
            try:
                async with self._http.stream("GET", f"/runs/{run_id}/events", headers={"Last-Event-ID": last_id}) as r:
                    r.raise_for_status()
                    async for event_id, kind, data in read_events(r):
                        last_id = event_id or last_id
                        if kind == END:
                            return
                        yield event_from_dict(json.loads(data))
            except httpx.TransportError:
                continue
        raise ConnectionError("Lost the connection to the daemon.")

    async def _get(self, path: str) -> Any:
        response = await self._http.get(path)
        response.raise_for_status()
        return response.json()

    async def _post(self, path: str, **kwargs: Any) -> Any:
        response = await self._http.post(path, **kwargs)
        response.raise_for_status()
        return response.json()


@asynccontextmanager
async def connect() -> AsyncIterator[DaemonClient]:
    """A client for the daemon on the Unix socket, starting the daemon first if it isn't running."""
    transport = httpx.AsyncHTTPTransport(uds=socket_path())
    headers = {CLIENT_HEADER: "cli"}
    async with httpx.AsyncClient(transport=transport, base_url=_BASE, timeout=_TIMEOUT, headers=headers) as http:
        if not await _is_ready(http):
            start_daemon()
            await wait_until_ready(lambda: _is_ready(http))
        yield DaemonClient(http)


async def _is_ready(http: httpx.AsyncClient) -> bool:
    try:
        return (await http.get("/health")).status_code == 200
    except httpx.TransportError:
        return False
