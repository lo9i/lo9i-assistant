"""MCP servers' web pages for paired devices, on their own port: the daemon's port plus
`PORT_OFFSET`, on localhost and, when configured, over HTTPS.

The pages get their own port so they're a different origin from the web app: a script in a page
(say, injected through data shown on it) can't call the daemon's API as the user. The web app shows
a page in an iframe; only the web app may frame it.

A request for /<name>/<path> must come from a paired device: its cookie, or its token as Authorization:
Bearer from a client that keeps its own (a browser extension, whose requests carry none of the
browser's cookies; /auth/pair/token). It goes to the server's
page on its Unix socket (core/mcp/pages.py) as /<path>, with X-Forwarded-Prefix: /<name> so the page
can link back. The device cookie never reaches the page, and the page can't set cookies: those
would be the web app's cookies too, since browsers don't separate cookies by port.

A request's answer is passed on as the page writes it: the page has `FIRST_BYTE_SECONDS` to start answering,
and then no time limit, so it can stream (Server-Sent Events, a long download). What goes both ways (a terminal)
is a WebSocket to the same path, passed through for as long as it lasts (daemon/page_sockets.py). Either one
ends when its device is revoked, as the API's event streams do.
"""

import asyncio
import html
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import ClientDisconnect, HTTPConnection, Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from assistant.core.agent import AssistantService, Device
from assistant.core.config import settings
from assistant.daemon import https, page_sockets
from assistant.daemon.auth import DeviceStreams, token_of
from assistant.daemon.http_server import Listener

logger = logging.getLogger(__name__)

# The web app finds pages at its own port plus this (clients/web/src/lib/pages.ts).
PORT_OFFSET = 1
# How long a page has to start answering; once it has, its answer may take as long as it streams.
FIRST_BYTE_SECONDS = 30
# Not passed on to the page: the daemon's credentials, and what the proxy sets itself.
_REQUEST_DROPPED = {"host", "cookie", "authorization", "x-forwarded-prefix", "content-length", "connection"}
_RESPONSE_DROPPED = {"set-cookie", "content-length", "transfer-encoding", "connection", "content-encoding"}
_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]
_NOT_PAIRED = "Open this page from the assistant's web app on a paired device."
# What the answer to a request whose browser left says, for the record (nginx's "client closed request").
_CLIENT_GONE = 499


def create_pages_app(service: AssistantService, streams: DeviceStreams | None = None) -> Starlette:
    """`streams` is the API's (daemon/auth.py), so revoking a device ends its pages' answers and WebSockets."""
    streams = streams or DeviceStreams()

    async def page(request: Request) -> Response:
        name, path = request.path_params["name"], request.path_params.get("path", "")
        device = await _device(service, request)
        if device is None:
            return PlainTextResponse(_NOT_PAIRED, 401)
        socket = service.pages.socket(name)
        if socket is None:
            why = "Its page isn't running: it may be starting."
            return _framed(_unavailable(request, 404, f"{name} has no page running.", why))
        return _framed(await _forward(request, socket, name, path, lambda body: streams.guard(body, device)))

    async def bare(request: Request) -> Response:
        return RedirectResponse(f"/{request.path_params['name']}/", 307)

    async def live(websocket: WebSocket) -> None:
        name, path = websocket.path_params["name"], websocket.path_params.get("path", "")
        device = await _device(service, websocket)
        if device is None:
            return await page_sockets.refuse(websocket, 401, _NOT_PAIRED)
        if not page_sockets.from_a_page(websocket, _web_app_origins(PORT_OFFSET)):
            return await page_sockets.refuse(websocket, 403, "Only the assistant's pages may open this.")
        socket = service.pages.socket(name)
        if socket is None:
            return await page_sockets.refuse(websocket, 404, f"{name} has no page running.")
        with streams.watching(device.id) as revoked:
            await page_sockets.pass_through(websocket, socket, name, path, revoked)

    return Starlette(
        routes=[
            Route("/{name}", bare, methods=_METHODS),
            Route("/{name}/{path:path}", page, methods=_METHODS),
            WebSocketRoute("/{name}/{path:path}", live),
        ]
    )


def listeners() -> list[Listener]:
    """Where the pages listen: localhost, and HTTPS when configured (last)."""
    found = [Listener(host="127.0.0.1", port=settings.daemon_port + PORT_OFFSET)]
    if https.enabled():
        found.append(https.listener(settings.https_port + PORT_OFFSET))
    return found


async def _device(service: AssistantService, request: HTTPConnection) -> Device | None:
    token = token_of(request)
    ip = request.client.host if request.client else ""
    return await service.device_for_token(token, ip) if token else None


async def _forward(
    request: Request, socket: Path, name: str, path: str, guard: Callable[[AsyncIterator[bytes]], AsyncIterator[bytes]]
) -> Response:
    """`guard` ends the answer's body early, when its device is revoked."""
    try:
        body = await request.body()
    except ClientDisconnect:
        # The browser left (the page closed, or it moved on) before sending all of it: nothing to pass on,
        # and nobody to answer.
        return Response(status_code=_CLIENT_GONE)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _REQUEST_DROPPED}
    headers["x-forwarded-prefix"] = f"/{name}"
    query = f"?{request.url.query}" if request.url.query else ""
    http = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds=str(socket)), base_url="http://page", timeout=None)
    sent = http.build_request(request.method, f"/{path}{query}", headers=headers, content=body)
    try:
        async with asyncio.timeout(FIRST_BYTE_SECONDS):
            answer = await http.send(sent, stream=True)
    except (httpx.TransportError, TimeoutError) as e:
        await http.aclose()
        return _not_answering(request, name, e)
    kept = {k: v for k, v in answer.headers.items() if k.lower() not in _RESPONSE_DROPPED}
    closed = BackgroundTask(_close, answer, http)
    return StreamingResponse(guard(answer.aiter_bytes()), answer.status_code, headers=kept, background=closed)


def _not_answering(request: Request, name: str, error: Exception) -> Response:
    if isinstance(error, TimeoutError):
        logger.warning("The page of %s didn't start answering within %ss", name, FIRST_BYTE_SECONDS)
        return _unavailable(request, 504, f"The page of {name} didn't answer in time.", "It didn't answer in time.")
    logger.warning("The page of %s didn't answer: %s", name, error)
    text = f"The page of {name} isn't answering yet. Try again in a moment."
    return _unavailable(request, 503, text, "It's starting, or starting again.")


def _unavailable(request: Request, status: int, text: str, why: str) -> Response:
    """`text` for a script's request (a page's htmx, a fetch), which shows it in its own way; for a browser opening
    the page, a notice in the app's look that tries again by itself (`_NOTICE`)."""
    navigating = "text/html" in request.headers.get("accept", "") and "hx-request" not in request.headers
    if not navigating:
        return PlainTextResponse(text, status)
    label = html.escape(_label(request.path_params["name"]))
    body = _NOTICE.format(title=f"{label} isn't ready", why=html.escape(why), retry=_RETRY_SECONDS)
    return HTMLResponse(body, status, headers={"retry-after": str(_RETRY_SECONDS)})


def _label(name: str) -> str:
    """As the web app's sidebar names it (clients/web/src/lib/pages.ts: pageLabel)."""
    return name[:1].upper() + name[1:].replace("-", " ").replace("_", " ")


# How often the notice tries the page again.
_RETRY_SECONDS = 3
# The app's look (clients/web/src/app.css): its tokens for both themes, and a glass card. Its theme is the one the
# web app gave the page (?theme=, then kept by the pages as lo9i.page-theme on this origin; core/mcp/install.py).
_NOTICE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script>
(() => {{
  let theme = new URLSearchParams(location.search).get("theme");
  try {{ theme = theme || localStorage.getItem("lo9i.page-theme"); }} catch {{}}
  const root = document.documentElement;
  const apply = (t) => (t === "light" ? (root.dataset.theme = "light") : delete root.dataset.theme);
  apply(theme);
  addEventListener("message", (e) => e.source === parent && e.data?.type === "lo9i:theme" && apply(e.data.theme));
  setTimeout(() => location.reload(), {retry}000);
}})();
</script>
<style>
:root {{ --text: #ffffff; --muted: #b6b9c0; --faint: #84878f; --accent: #30d158;
  --glass: rgba(26, 25, 27, 0.58); --glass-border: rgba(255, 255, 255, 0.08); color-scheme: dark; }}
:root[data-theme="light"] {{ --text: #0f172a; --muted: #475569; --faint: #94a3b8; --accent: #16a34a;
  --glass: rgba(255, 255, 255, 0.62); --glass-border: rgba(15, 23, 42, 0.1); color-scheme: light; }}
html, body {{ margin: 0; height: 100%; background: transparent; }}
body {{ display: flex; align-items: center; justify-content: center; padding: 16px; box-sizing: border-box;
  font: 0.85rem/1.5 "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--text); }}
.card {{ display: flex; gap: 14px; align-items: flex-start; max-width: 26rem; padding: 20px 24px; border-radius: 16px;
  background: var(--glass); border: 1px solid var(--glass-border);
  backdrop-filter: blur(20px) saturate(160%); -webkit-backdrop-filter: blur(20px) saturate(160%); }}
.spin {{ flex: none; width: 18px; height: 18px; margin-top: 1px; border-radius: 50%;
  border: 2px solid color-mix(in srgb, var(--accent) 25%, transparent); border-top-color: var(--accent);
  animation: spin 0.9s linear infinite; }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
h1 {{ margin: 0 0 4px; font-size: 1rem; font-weight: 600; line-height: 1.3; }}
p {{ margin: 0; color: var(--muted); }}
.small {{ margin-top: 8px; font-size: 0.75rem; color: var(--faint); }}
</style></head>
<body><div class="card" role="status"><span class="spin" aria-hidden="true"></span><div>
<h1>{title}</h1><p>{why}</p><p class="small">Trying again every few seconds.</p>
</div></div></body></html>
"""


async def _close(answer: httpx.Response, http: httpx.AsyncClient) -> None:
    """Once the answer was passed on, or the browser left in the middle of it."""
    await answer.aclose()
    await http.aclose()


def _framed(response: Response) -> Response:
    """Only the web app may show it in a frame."""
    response.headers["content-security-policy"] = f"frame-ancestors {' '.join(_web_app_origins())}"
    response.headers["x-content-type-options"] = "nosniff"
    return response


def _web_app_origins(offset: int = 0) -> list[str]:
    """The web app's origins; with `PORT_OFFSET`, the pages'."""
    port = settings.daemon_port + offset
    origins = [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]
    if https.enabled():
        origins.append(f"https://{settings.https_host}:{settings.https_port + offset}")
    return origins
