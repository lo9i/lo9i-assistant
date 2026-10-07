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
"""

import logging
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

from assistant.core.agent import AssistantService, Device
from assistant.core.config import settings
from assistant.daemon import https
from assistant.daemon.auth import token_of

logger = logging.getLogger(__name__)

# The web app finds pages at its own port plus this (clients/web/src/lib/pages.ts).
PORT_OFFSET = 1
_TIMEOUT = httpx.Timeout(30)
# Not passed on to the page: the daemon's credentials, and what the proxy sets itself.
_REQUEST_DROPPED = {"host", "cookie", "authorization", "x-forwarded-prefix", "content-length", "connection"}
_RESPONSE_DROPPED = {"set-cookie", "content-length", "transfer-encoding", "connection", "content-encoding"}
_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]


def create_pages_app(service: AssistantService) -> Starlette:
    async def page(request: Request) -> Response:
        name, path = request.path_params["name"], request.path_params.get("path", "")
        if await _device(service, request) is None:
            return PlainTextResponse("Open this page from the assistant's web app on a paired device.", 401)
        socket = service.pages.socket(name)
        if socket is None:
            return PlainTextResponse(f"{name} has no page running.", 404)
        return _framed(await _forward(request, socket, name, path))

    async def bare(request: Request) -> Response:
        return RedirectResponse(f"/{request.path_params['name']}/", 307)

    return Starlette(
        routes=[
            Route("/{name}", bare, methods=_METHODS),
            Route("/{name}/{path:path}", page, methods=_METHODS),
        ]
    )


def ports() -> list[dict]:
    """uvicorn bind arguments for the pages listeners: localhost, and HTTPS when configured."""
    binds: list[dict] = [{"host": "127.0.0.1", "port": settings.daemon_port + PORT_OFFSET}]
    if https.enabled():
        binds.append({**https.bind(), "port": settings.https_port + PORT_OFFSET})
    return binds


async def _device(service: AssistantService, request: Request) -> Device | None:
    token = token_of(request)
    ip = request.client.host if request.client else ""
    return await service.device_for_token(token, ip) if token else None


async def _forward(request: Request, socket: Path, name: str, path: str) -> Response:
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _REQUEST_DROPPED}
    headers["x-forwarded-prefix"] = f"/{name}"
    transport = httpx.AsyncHTTPTransport(uds=str(socket))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://page", timeout=_TIMEOUT) as http:
            query = f"?{request.url.query}" if request.url.query else ""
            answer = await http.request(
                request.method, f"/{path}{query}", headers=headers, content=await request.body()
            )
    except httpx.TransportError as e:
        logger.warning("The page of %s didn't answer: %s", name, e)
        return PlainTextResponse(f"The page of {name} isn't answering yet. Try again in a moment.", 503)
    kept = {k: v for k, v in answer.headers.items() if k.lower() not in _RESPONSE_DROPPED}
    return Response(answer.content, answer.status_code, headers=kept)


def _framed(response: Response) -> Response:
    """Only the web app may show it in a frame."""
    response.headers["content-security-policy"] = f"frame-ancestors {' '.join(_web_app_origins())}"
    response.headers["x-content-type-options"] = "nosniff"
    return response


def _web_app_origins() -> list[str]:
    origins = [f"http://127.0.0.1:{settings.daemon_port}", f"http://localhost:{settings.daemon_port}"]
    if https.enabled():
        origins.append(f"https://{settings.https_host}:{settings.https_port}")
    return origins
