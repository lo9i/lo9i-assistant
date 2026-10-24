"""Event streams resume after dropped connections, and give up with DaemonUnavailableError."""

import httpx
import pytest

from assistant.client.daemon_client.reconnect import ReconnectPolicy, resumable_events
from assistant.client.daemon_client.transport import Transport
from assistant.client.errors import DaemonUnavailableError

_NOW = ReconnectPolicy(delay_seconds=0, attempts=3)


def _transport(handler) -> Transport:
    return Transport(httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://lo9i"))


async def _read(transport: Transport, policy: ReconnectPolicy = _NOW, stop_at: str = "end") -> list[str]:
    kinds = []
    async for kind, data in resumable_events(transport, "/runs/r/events", policy):
        kinds.append(f"{kind}:{data}")
        if kind == stop_at:
            break
    return kinds


async def test_a_dropped_stream_resumes_after_the_last_event():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Last-Event-ID"])
        if len(seen) == 1:
            return httpx.Response(200, text="id: 1\ndata: a\n\n")  # ends without "end": dropped
        return httpx.Response(200, text="id: 2\ndata: b\n\nid: 3\nevent: end\ndata: {}\n\n")

    assert await _read(_transport(handler)) == ["message:a", "message:b", "end:{}"]
    assert seen == ["0", "1"]


async def test_gives_up_after_the_policy_attempts():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("refused")

    with pytest.raises(DaemonUnavailableError):
        await _read(_transport(handler))
    assert len(calls) == 3


async def test_client_errors_are_not_retried():
    with pytest.raises(httpx.HTTPStatusError):
        await _read(_transport(lambda request: httpx.Response(404, json={"detail": "Unknown run"})))


async def test_requests_to_an_unreachable_daemon_raise_daemon_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(DaemonUnavailableError):
        await _transport(handler).request("GET", "/memory")


async def test_a_stream_read_from_now_sends_no_id_until_it_has_one():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Last-Event-ID"))
        return httpx.Response(200, text="id: 9\ndata: a\n\n" if len(seen) == 1 else "id: 10\nevent: end\ndata: {}\n\n")

    kinds = []
    async for kind, _ in resumable_events(_transport(handler), "/events", _NOW, after=""):
        kinds.append(kind)
        if kind == "end":
            break
    assert kinds == ["message", "end"] and seen == [None, "9"]


async def test_the_reader_hears_when_the_stream_drops_and_opens_again():
    heard, calls = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("refused")  # the daemon is restarting
        return httpx.Response(200, text="id: 1\nevent: end\ndata: {}\n\n")

    events = resumable_events(
        _transport(handler), "/events", _NOW, on_open=lambda: heard.append("open"), on_lost=lambda: heard.append("lost")
    )
    async for kind, _ in events:
        if kind == "end":
            break
    assert heard == ["lost", "open"]
