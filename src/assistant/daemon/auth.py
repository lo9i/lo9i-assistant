"""Who may use the daemon.

The Unix socket is trusted: only the owner's user can open it. Every network request, on the
localhost port or HTTPS, must come from a paired device: a browser that entered a one-time code
from a trusted client and got a token, kept in a cookie. 127.0.0.1 isn't trusted, because port
forwarding and proxies make remote traffic arrive from there.

Without a device, the network only reaches /health, pairing, and the web UI's files (its login
page). Revoking a device ends its open event streams.

A channel plugin's process (core/channels/) sends the token the daemon gave it when it started
instead. That token reaches only its own channel's routes, `/channels/<name>/...`.
"""

import asyncio
import contextlib
import logging
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.types import ASGIApp, Receive, Scope, Send

from assistant.core.agent import AssistantService, Device, DeviceError, PairingCode
from assistant.core.devices import UNUSED_LIFETIME
from assistant.daemon.web_ui import is_web_ui

logger = logging.getLogger(__name__)

COOKIE = "lo9i_device"
_TRUSTED = "lo9i.trusted"
# A sign-in's last step comes from the browser that signed in, maybe unpaired; its one-time state
# proves it (core/oauth.py).
_OPEN_PATHS = {"/health", "/auth/pair", "/oauth/finish"}


class PairRequest(BaseModel):
    code: str
    name: str


class Revoked(BaseModel):
    ok: bool = True


class Me(BaseModel):
    """The caller: a trusted client (Unix socket), or the paired device it is."""

    trusted: bool
    device: Device | None


def trusted(app: ASGIApp) -> ASGIApp:
    """Marks every request as trusted. Wraps the app on the Unix socket only."""

    async def marked(scope: Scope, receive: Receive, send: Send) -> None:
        await app({**scope, _TRUSTED: True} if scope["type"] == "http" else scope, receive, send)

    return marked


def is_trusted(request: Request) -> bool:
    return bool(request.scope.get(_TRUSTED))


def channel_of(request: Request) -> str | None:
    """The channel plugin making the request, when it carries a channel's token."""
    return getattr(request.state, "channel", None)


def device_of(request: Request) -> Device | None:
    """The paired device making a network request; None on the Unix socket."""
    return getattr(request.state, "device", None)


class PairingLimiter:
    """Wrong codes allowed per IP and in total within a window, so a code can't be guessed."""

    def __init__(
        self,
        per_ip: int = 5,
        total: int = 20,
        window_seconds: float = 900,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._per_ip, self._total, self._window, self._clock = per_ip, total, window_seconds, clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def blocked(self, ip: str) -> bool:
        self._forget_old()
        return len(self._failures[ip]) >= self._per_ip or self._count() >= self._total

    def failed(self, ip: str) -> None:
        self._failures[ip].append(self._clock())

    def _count(self) -> int:
        return sum(len(times) for times in self._failures.values())

    def _forget_old(self) -> None:
        oldest = self._clock() - self._window
        for times in self._failures.values():
            while times and times[0] < oldest:
                times.popleft()


class DeviceStreams:
    """The event streams each device has open, so revoking it ends them at once."""

    def __init__(self) -> None:
        self._ends: dict[str, set[asyncio.Event]] = defaultdict(set)

    async def guard[T](self, events: AsyncIterator[T], device: Device | None) -> AsyncIterator[T]:
        if device is None:
            async for item in events:
                yield item
            return
        ended = asyncio.Event()
        self._ends[device.id].add(ended)
        try:
            async for item in _until(events, ended):
                yield item
        finally:
            self._ends[device.id].discard(ended)

    def end(self, device_id: str) -> None:
        for ended in self._ends.pop(device_id, set()):
            ended.set()


def require_device(app: FastAPI, service: AssistantService) -> None:
    @app.middleware("http")
    async def check(request: Request, call_next):
        if is_trusted(request) or request.url.path in _OPEN_PATHS or is_web_ui(request.url.path):
            return await call_next(request)
        token = _token(request)
        if token and (channel := service.channels_hub.channel_for(token)) is not None:
            return await _as_channel(request, call_next, channel)
        device = await service.device_for_token(token, _ip(request)) if token else None
        if device is None:
            return JSONResponse({"detail": "This device isn't paired."}, status_code=401)
        request.state.device = device
        response = await call_next(request)
        if request.cookies.get(COOKIE):
            _set_cookie(response, token)  # Kept for as long as the device is in use.
        return response


async def _as_channel(request: Request, call_next, channel: str):
    if not request.url.path.startswith(f"/channels/{channel}/"):
        return JSONResponse({"detail": "A channel's token reaches only its own channel's routes."}, status_code=403)
    request.state.channel = channel
    return await call_next(request)


def add_device_routes(app: FastAPI, service: AssistantService, streams: DeviceStreams) -> None:
    limiter = PairingLimiter()

    @app.post("/auth/pair")
    async def pair(body: PairRequest, request: Request, response: Response) -> Device:
        """Pairs this browser with a code from a trusted client, and sets its token cookie."""
        ip = _ip(request)
        if limiter.blocked(ip):
            raise HTTPException(429, "Too many wrong codes. Wait a few minutes and try again.")
        try:
            device, token = await service.pair_device(body.code, body.name, ip)
        except DeviceError as e:
            limiter.failed(ip)
            logger.warning("Wrong pairing code from %s", ip)
            raise HTTPException(400, str(e)) from e
        logger.info("Paired device %s (%s) from %s", device.name, device.id, ip)
        _set_cookie(response, token)
        return device

    @app.get("/auth/me")
    async def me(request: Request) -> Me:
        return Me(trusted=is_trusted(request), device=device_of(request))

    @app.post("/auth/logout")
    async def logout(request: Request, response: Response) -> Me:
        """Unpairs the calling device."""
        device = device_of(request)
        if device is not None:
            await _revoke(service, streams, device.id)
        response.delete_cookie(COOKIE, path="/")
        return Me(trusted=is_trusted(request), device=None)

    _add_device_list_routes(app, service, streams)


def _add_device_list_routes(app: FastAPI, service: AssistantService, streams: DeviceStreams) -> None:
    @app.get("/devices")
    async def device_list() -> list[Device]:
        return await service.list_devices()

    @app.post("/devices/pairing")
    async def open_pairing() -> PairingCode:
        """A one-time code for pairing another device."""
        return await service.open_device_pairing()

    @app.delete("/devices/{device_id}")
    async def revoke(device_id: str) -> Revoked:
        await _revoke(service, streams, device_id)
        return Revoked()


async def _revoke(service: AssistantService, streams: DeviceStreams, device_id: str) -> None:
    try:
        await service.revoke_device(device_id)
    except DeviceError as e:
        raise HTTPException(404, str(e)) from e
    streams.end(device_id)
    logger.info("Revoked device %s", device_id)


async def _until[T](events: AsyncIterator[T], ended: asyncio.Event) -> AsyncIterator[T]:
    """The events until `ended` is set."""
    iterator = aiter(events)
    stop = asyncio.ensure_future(ended.wait())
    following: asyncio.Future[Any] | None = None
    try:
        while True:
            following = asyncio.ensure_future(anext(iterator))
            await asyncio.wait({following, stop}, return_when=asyncio.FIRST_COMPLETED)
            if not following.done():
                return
            try:
                item = following.result()
            except StopAsyncIteration:
                return
            yield item
    finally:
        stop.cancel()
        await _stop(following)


async def _stop(following: asyncio.Future[Any] | None) -> None:
    """Ends a pending read of the guarded stream, so its cleanup runs. Left pending, the task would hold
    the stream open after its reader left (a disconnected browser stayed listed as a connected client)."""
    if following is None or following.done():
        return
    following.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await following


def _token(request: Request) -> str:
    bearer = request.headers.get("authorization", "")
    return request.cookies.get(COOKIE) or bearer.removeprefix("Bearer ").strip()


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _set_cookie(response: Response, token: str) -> None:
    lifetime = int(UNUSED_LIFETIME / timedelta(seconds=1))
    response.set_cookie(COOKIE, token, max_age=lifetime, path="/", secure=True, httponly=True, samesite="strict")
