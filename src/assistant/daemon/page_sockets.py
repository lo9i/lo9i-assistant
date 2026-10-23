"""Live connections to MCP servers' pages: a WebSocket from the browser, passed through to the page on its
Unix socket and back, message by message, for as long as either side keeps it open. Unlike a request
(daemon/pages.py), it has no time limit: a terminal in a page stays open for hours.

The pages port takes it under the same rules as its requests: a paired device, and the page reached as
/<path> with X-Forwarded-Prefix: /<name>, without the device's cookie. Revoking the device closes it.

A browser opens a WebSocket to any address with the user's cookies and no CORS check, and the cookie's
SameSite counts every port of a host as one site, so a browser's connection must come from a page of these
(its Origin): not another site, nor another server on 127.0.0.1. A client that isn't a browser sends no
Origin and proves itself with its token (Authorization: Bearer).
"""

import asyncio
import contextlib
import logging
from pathlib import Path
from urllib.parse import quote, urlsplit

from starlette.responses import PlainTextResponse
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import ClientConnection, unix_connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus
from websockets.typing import Subprotocol

logger = logging.getLogger(__name__)

# Waits only for the page to take the connection; once open, it stays as long as both sides want it.
_OPEN_SECONDS = 10
# uvicorn's limit for what the browser sends, so both directions take the same.
_MAX_MESSAGE = 16 * 1024 * 1024
# Codes a close frame may carry (RFC 6455 7.4); the others only describe how a connection ended.
_UNSENDABLE = {1005, 1006, 1015}
_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}


def from_a_page(websocket: WebSocket, origins: list[str]) -> bool:
    """Whether the connection may come in: from one of the pages' origins, or from a client that isn't a
    browser (no Origin)."""
    origin = websocket.headers.get("origin")
    return origin is None or _origin(origin) in {_origin(o) for o in origins}


async def refuse(websocket: WebSocket, status: int, text: str) -> None:
    """Answers the opening request with an HTTP error, so the browser's console says why."""
    if "websocket.http.response" in websocket.scope.get("extensions", {}):
        await websocket.send_denial_response(PlainTextResponse(text, status))
    else:
        await websocket.close(1008, text)


async def pass_through(websocket: WebSocket, socket: Path, name: str, path: str, revoked: asyncio.Event) -> None:
    """Connects the browser to the page until either one closes, or the device is revoked."""
    try:
        page = await _connect(websocket, socket, name, path)
    except InvalidStatus as e:
        await refuse(websocket, e.response.status_code, f"The page of {name} refused the connection.")
        return
    except (OSError, TimeoutError, InvalidHandshake) as e:
        logger.warning("The page of %s didn't take a live connection: %s", name, e)
        await refuse(websocket, 503, f"The page of {name} isn't answering yet. Try again in a moment.")
        return
    async with page:
        await websocket.accept(subprotocol=page.subprotocol)
        await _relay(websocket, page, revoked)


async def _connect(websocket: WebSocket, socket: Path, name: str, path: str) -> ClientConnection:
    query = websocket.url.query
    uri = f"ws://page/{quote(path)}" + (f"?{query}" if query else "")
    asked = [Subprotocol(p) for p in websocket.scope.get("subprotocols", [])]
    return await unix_connect(
        str(socket),
        uri,
        additional_headers={"X-Forwarded-Prefix": f"/{name}"},
        subprotocols=asked or None,
        user_agent_header=websocket.headers.get("user-agent"),
        open_timeout=_OPEN_SECONDS,
        # A local socket: a page that goes away closes it, so no pings, which would close a connection
        # whose page was busy for a while.
        ping_interval=None,
        max_size=_MAX_MESSAGE,
        proxy=None,
    )


async def _relay(browser: WebSocket, page: ClientConnection, revoked: asyncio.Event) -> None:
    tasks = [
        asyncio.create_task(_to_page(browser, page)),
        asyncio.create_task(_to_browser(page, browser)),
        asyncio.create_task(revoked.wait()),
    ]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if revoked.is_set():
        await _close(browser, 1008, "This device was unpaired.")


async def _to_page(browser: WebSocket, page: ClientConnection) -> None:
    """What the browser sends, until it leaves; then the page is told how."""
    while True:
        message = await browser.receive()
        if message["type"] == "websocket.disconnect":
            await page.close(_sendable(message.get("code", 1000), 1001), message.get("reason") or "")
            return
        text, data = message.get("text"), message.get("bytes")
        await page.send(text if text is not None else data or b"")


async def _to_browser(page: ClientConnection, browser: WebSocket) -> None:
    """What the page sends, until it closes; then the browser is closed the same way."""
    try:
        async for message in page:
            if isinstance(message, str):
                await browser.send_text(message)
            else:
                await browser.send_bytes(message)
    except ConnectionClosed:
        pass
    await _close(browser, _sendable(page.close_code or 1000, 1011), page.close_reason or "")


async def _close(browser: WebSocket, code: int, reason: str) -> None:
    # The browser may have left meanwhile; there's no one to tell then.
    with contextlib.suppress(RuntimeError, WebSocketDisconnect):
        await browser.close(code, reason)


def _sendable(code: int, otherwise: int) -> int:
    return otherwise if code in _UNSENDABLE else code


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url.lower())
    try:
        port = parts.port or _DEFAULT_PORTS.get(parts.scheme)
    except ValueError:
        port = None
    return parts.scheme, parts.hostname or "", port
