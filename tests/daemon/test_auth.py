"""Network access: only paired devices get in, pairing codes can't be guessed or reused, and
revoking a device locks it out. The Unix socket stays trusted."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from assistant.core import devices
from assistant.daemon.api import create_app
from assistant.daemon.auth import COOKIE, DeviceStreams, PairingLimiter, trusted
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER


@pytest.fixture
def app(service):
    return create_app(service, RunHub())


def _http(app, ip: str = "203.0.113.7") -> httpx.AsyncClient:
    """A browser on another host, over HTTPS (Secure cookies are only sent back over HTTPS)."""
    transport = httpx.ASGITransport(app=app, client=(ip, 51000))
    return httpx.AsyncClient(transport=transport, base_url="https://localhost", headers={CLIENT_HEADER: "web"})


def _socket(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=trusted(app))
    return httpx.AsyncClient(transport=transport, base_url="http://lo9i", headers={CLIENT_HEADER: "cli"})


async def _code(app) -> str:
    async with _socket(app) as cli:
        return (await cli.post("/devices/pairing")).json()["code"]


async def test_a_browser_pairs_with_a_code_from_a_trusted_client(app):
    async with _http(app) as browser:
        assert (await browser.get("/conversations")).status_code == 401
        assert (await browser.get("/health")).status_code == 200
        code = await _code(app)
        response = await browser.post("/auth/pair", json={"code": code.lower(), "name": "Laptop"})
        assert response.status_code == 200 and response.json()["name"] == "Laptop"
        cookie = response.headers["set-cookie"]
        assert f"{COOKIE}=" in cookie and "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        assert response.headers["strict-transport-security"].startswith("max-age=")
        assert (await browser.get("/conversations")).status_code == 200
        assert (await browser.get("/auth/me")).json()["device"]["name"] == "Laptop"
    async with _http(app) as other:
        assert (await other.post("/auth/pair", json={"code": code, "name": "Thief"})).status_code == 400


async def test_wrong_codes_are_limited_per_address(app):
    await _code(app)
    async with _http(app) as browser:
        for _ in range(5):
            assert (await browser.post("/auth/pair", json={"code": "AAAA-AAAA", "name": "x"})).status_code == 400
        assert (await browser.post("/auth/pair", json={"code": "AAAA-AAAA", "name": "x"})).status_code == 429


async def test_revoking_a_device_locks_it_out(app):
    async with _http(app) as browser:
        await browser.post("/auth/pair", json={"code": await _code(app), "name": "Phone"})
        async with _socket(app) as cli:
            [device] = (await cli.get("/devices")).json()
            assert device["last_ip"] == "203.0.113.7"
            assert (await cli.delete(f"/devices/{device['id']}")).status_code == 200
            assert (await cli.get("/devices")).json() == []
        assert (await browser.get("/conversations")).status_code == 401


async def test_a_paired_browser_can_log_out_and_pair_others(app):
    async with _http(app) as browser:
        await browser.post("/auth/pair", json={"code": await _code(app), "name": "Desk"})
        assert (await browser.post("/devices/pairing")).status_code == 200
        assert (await browser.post("/auth/logout")).status_code == 200
        assert (await browser.get("/conversations")).status_code == 401


async def test_the_unix_socket_needs_no_device(app):
    async with _socket(app) as cli:
        me = (await cli.get("/auth/me")).json()
        assert me == {"trusted": True, "device": None}
        assert (await cli.get("/conversations")).status_code == 200


async def test_tokens_and_codes_are_stored_only_as_hashes(service):
    now = datetime.now(UTC)
    pairing = await devices.open_pairing(service.store, now)
    _, token = await devices.add(service.store, "Laptop", "1.2.3.4", now)
    stored = str([i.value for i in await service.store.asearch(("devices",))]) + str(
        await service.store.aget(("device_pairing",), "code")
    )
    assert token not in stored and pairing.code.replace("-", "") not in stored


async def test_a_device_unused_for_too_long_must_pair_again(service):
    then = datetime.now(UTC) - devices.UNUSED_LIFETIME - timedelta(days=1)
    _, token = await devices.add(service.store, "Old", "1.2.3.4", then)
    assert await devices.find(service.store, token, "1.2.3.4", datetime.now(UTC)) is None


async def test_an_expired_code_is_refused(service):
    then = datetime.now(UTC) - timedelta(minutes=11)
    pairing = await devices.open_pairing(service.store, then)
    assert not await devices.take_pairing(service.store, pairing.code, datetime.now(UTC))


def test_the_limiter_forgets_old_failures():
    now = [0.0]
    limiter = PairingLimiter(per_ip=2, total=3, window_seconds=60, clock=lambda: now[0])
    limiter.failed("a")
    limiter.failed("a")
    assert limiter.blocked("a") and not limiter.blocked("b")
    limiter.failed("b")
    assert limiter.blocked("c")  # three failures in total
    now[0] = 61
    assert not limiter.blocked("a") and not limiter.blocked("c")


async def test_revoking_ends_the_devices_open_streams():
    streams = DeviceStreams()
    device = devices.Device("d1", "Laptop", "", "", "")

    async def forever():
        yield 1
        await asyncio.Event().wait()
        yield 2

    received = []

    async def read():
        async for item in streams.guard(forever(), device):
            received.append(item)

    reader = asyncio.create_task(read())
    while not received:
        await asyncio.sleep(0)
    streams.end("d1")
    await asyncio.wait_for(reader, 1)
    assert received == [1]


async def test_a_device_stream_its_reader_drops_closes_the_stream_it_guards():
    """A browser that disconnects cancels the response; what the stream holds (a connected client) must go too."""
    streams = DeviceStreams()
    device = devices.Device("d1", "Laptop", "", "", "")
    closed = asyncio.Event()

    async def forever():
        try:
            yield 1
            await asyncio.Event().wait()
        finally:
            closed.set()

    async def read():
        async for _ in streams.guard(forever(), device):
            pass

    reader = asyncio.create_task(read())
    for _ in range(5):  # until it waits for the second item
        await asyncio.sleep(0)
    reader.cancel()
    await asyncio.wait_for(closed.wait(), 1)


async def test_a_sign_in_finishes_from_an_unpaired_browser_but_only_starts_from_a_paired_one(app):
    sign_in = {
        "provider": "google",
        "client_id": "c",
        "redirect_uri": "http://localhost:8765/app/oauth",
        "address": "me@gmail.com",
    }
    async with _http(app) as browser:
        assert (await browser.post("/integrations/email/oauth/start", json=sign_in)).status_code == 401
        # The one-time state is the proof: a wrong one is refused, not the browser.
        finish = await browser.post("/oauth/finish", json={"state": "guess", "code": "x"})
        assert finish.status_code == 400 and "expired" in finish.json()["detail"]


async def test_a_client_that_keeps_its_own_token_pairs_for_it_and_sends_it_as_a_bearer(app):
    async with _http(app) as extension:
        response = await extension.post(
            "/auth/pair/token", json={"code": await _code(app), "name": "Watchlist extension"}
        )
        assert response.status_code == 200 and "set-cookie" not in response.headers
        paired = response.json()
        assert paired["device"]["name"] == "Watchlist extension" and paired["token"]
        bearer = {"Authorization": f"Bearer {paired['token']}"}
        assert (await extension.get("/auth/me", headers=bearer)).json()["device"]["name"] == "Watchlist extension"
        assert (await extension.post("/auth/pair/token", json={"code": "AAAA-AAAA", "name": "x"})).status_code == 400
