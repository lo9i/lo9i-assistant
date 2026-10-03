"""Signing in to a remote MCP server with OAuth: the server asks to sign in, the user signs in from a
browser, the tokens are kept encrypted and refreshed at the authorization server, and a refused
refresh waits for the user again. The MCP server and its authorization server run in-process."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server import MCPServer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from assistant.core import secret_store
from assistant.core.agent import (
    Alert,
    AssistantService,
    McpServer,
    McpServerChanges,
    McpServerError,
    SignInError,
)
from assistant.core.mcp import hub as hub_module

URL = "https://notes.test/mcp"
ISSUER = "https://auth.test"
REDIRECT = "https://board.ts.net:8443/app/oauth"


class _OAuthServer:
    """An MCP server at notes.test that wants a bearer token, and its authorization server at
    auth.test: discovery, client registration, codes, tokens and refreshes."""

    def __init__(self) -> None:
        self.registrations: list[dict] = []
        self.token_requests: list[dict] = []
        self.tokens: set[str] = set()
        self.refuse_refresh = False
        self.open = False
        self._issued = 0
        self._mcp = MCPServer("notes")

        @self._mcp.tool()
        def read_notes() -> str:
            """Read all notes."""
            return "no notes"

        self._inner = self._mcp.streamable_http_app(
            stateless_http=True, json_response=True, streamable_http_path="/mcp", host="notes.test"
        )
        self._auth = Starlette(
            routes=[
                Route("/.well-known/oauth-authorization-server", self._metadata),
                Route("/register", self._register, methods=["POST"]),
                Route("/token", self._token, methods=["POST"]),
            ]
        )
        self._resource = Starlette(routes=[Route("/.well-known/oauth-protected-resource/mcp", self._protected)])

    async def run(self, stop: asyncio.Event) -> None:
        """The MCP server's session manager must start and stop in one task."""
        async with self._mcp.session_manager.run():
            await stop.wait()

    async def __call__(self, scope, receive, send) -> None:
        host = dict(scope.get("headers", [])).get(b"host", b"").decode()
        if host == "auth.test":
            return await self._auth(scope, receive, send)
        if scope.get("path") == "/mcp":
            return await self._guarded(scope, receive, send)
        await self._resource(scope, receive, send)

    async def _guarded(self, scope, receive, send) -> None:
        token = dict(scope["headers"]).get(b"authorization", b"").decode().removeprefix("Bearer ")
        if self.open or token in self.tokens:
            return await self._inner(scope, receive, send)
        challenge = 'Bearer resource_metadata="https://notes.test/.well-known/oauth-protected-resource/mcp"'
        await JSONResponse({"error": "unauthorized"}, 401, {"WWW-Authenticate": challenge})(scope, receive, send)

    async def _protected(self, _: Request) -> JSONResponse:
        return JSONResponse({"resource": URL, "authorization_servers": [ISSUER]})

    async def _metadata(self, _: Request) -> JSONResponse:
        return JSONResponse(
            {
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
                "registration_endpoint": f"{ISSUER}/register",
                "response_types_supported": ["code"],
                "code_challenge_methods_supported": ["S256"],
            }
        )

    async def _register(self, request: Request) -> JSONResponse:
        body = await request.json()
        self.registrations.append(body)
        return JSONResponse({**body, "client_id": f"client-{len(self.registrations)}"}, 201)

    async def _token(self, request: Request) -> JSONResponse:
        form = dict(await request.form())
        self.token_requests.append(form)
        if form.get("code") == "bad" or (form["grant_type"] == "refresh_token" and self.refuse_refresh):
            return JSONResponse({"error": "invalid_grant"}, 400)
        self._issued += 1
        token = f"access-{self._issued}"
        self.tokens.add(token)
        return JSONResponse(
            {"access_token": token, "token_type": "bearer", "expires_in": 3600, "refresh_token": "refresh.1"}
        )


@pytest.fixture
async def oauth_server() -> AsyncIterator[_OAuthServer]:
    fake = _OAuthServer()
    stop = asyncio.Event()
    task = asyncio.create_task(fake.run(stop))
    yield fake
    stop.set()
    await task


@pytest.fixture
async def service(script, digests, titles, oauth_server, monkeypatch) -> AsyncIterator[AssistantService]:
    """The service with its MCP hub running, remote servers reached in-process."""

    @asynccontextmanager
    async def transport(server: McpServer, auth: httpx2.Auth | None) -> AsyncIterator:
        async with (
            httpx2.AsyncClient(transport=httpx2.ASGITransport(app=oauth_server), auth=auth) as http,
            streamable_http_client(server.url, http_client=http) as streams,
        ):
            yield streams

    monkeypatch.setattr(
        hub_module,
        "open_client",
        lambda server, handler, auth: Client(transport(server, auth), message_handler=handler),
    )
    async with AssistantService.open() as svc:
        stop = asyncio.Event()
        task = asyncio.create_task(svc.mcp.run(stop))
        yield svc
        stop.set()
        await task


@pytest.fixture
def signed_out(service, monkeypatch) -> list[dict[str, Any]]:
    """The `signed_out` events the service publishes."""
    seen: list[dict[str, Any]] = []
    publish = service.bus.publish

    def record(kind: str, **data: Any) -> None:
        if kind == "signed_out":
            seen.append(data)
        publish(kind, **data)

    monkeypatch.setattr(service.bus, "publish", record)
    return seen


async def _alerted(service: AssistantService) -> list[Alert]:
    for _ in range(200):
        if found := await service.alerts():
            return found
        await asyncio.sleep(0.02)
    raise TimeoutError("no alert")


async def _status(service: AssistantService, wanted: str) -> Any:
    for _ in range(200):
        [server] = await service.mcp_servers()
        if server.status == wanted:
            return server
        await asyncio.sleep(0.02)
    raise TimeoutError(f"the server never got to {wanted}")


async def _add(service: AssistantService) -> None:
    await service.add_mcp_server(McpServer(name="notes", url=URL))
    await _status(service, "needs_sign_in")


async def _sign_in(service: AssistantService, code: str = "code-1") -> dict[str, list[str]]:
    page = await service.start_mcp_sign_in("notes", REDIRECT)
    query = parse_qs(urlparse(page).query)
    await service.finish_sign_in(query["state"][0], code)
    return query


async def _saved(service: AssistantService) -> dict:
    return json.loads(await secret_store.get(service.store, service.secrets, "mcp:notes"))


async def test_a_server_that_asks_to_sign_in_can_be_added_and_waits_without_registering(
    service, oauth_server, signed_out
):
    probe = await service.probe_mcp_server(McpServer(name="notes", url=URL))
    assert probe.sign_in and probe.tools == []
    await _add(service)
    [server] = await service.mcp_servers()
    assert "asks you to sign in" in server.error and server.failures == 0
    assert oauth_server.registrations == []
    # The user is adding it and sees it asks: not an alert.
    assert signed_out == [] and await service.alerts() == []


async def test_signing_in_registers_trades_the_code_and_connects(service, oauth_server):
    await _add(service)
    query = await _sign_in(service)
    assert query["redirect_uri"] == [REDIRECT] and query["code_challenge_method"] == ["S256"]
    assert query["resource"] == [URL]
    assert oauth_server.registrations[0]["redirect_uris"] == [REDIRECT]
    assert oauth_server.registrations[0]["application_type"] == "web"
    exchange = oauth_server.token_requests[0]
    assert (exchange["grant_type"], exchange["code"], exchange["redirect_uri"]) == (
        "authorization_code",
        "code-1",
        REDIRECT,
    )
    server = await _status(service, "connected")
    assert [t.name for t in server.tools] == ["read_notes"]
    saved = await _saved(service)
    assert saved["tokens"]["refresh_token"] == "refresh.1" and saved["metadata"]["token_endpoint"] == f"{ISSUER}/token"
    raw = await service.store.aget(("secrets",), "mcp:notes")
    assert raw is not None and "refresh.1" not in json.dumps(raw.value)  # encrypted: Fernet output has no "."


async def test_an_expired_token_is_refreshed_at_the_saved_endpoint(service, oauth_server):
    await _add(service)
    await _sign_in(service)
    await _status(service, "connected")
    saved = await _saved(service)
    saved["expires_at"] = time.time() - 10
    await secret_store.put(service.store, service.secrets, "mcp:notes", json.dumps(saved))
    oauth_server.tokens.clear()
    await service.mcp.restart("notes")
    await _status(service, "connected")
    refresh = oauth_server.token_requests[-1]
    assert (refresh["grant_type"], refresh["refresh_token"]) == ("refresh_token", "refresh.1")
    assert (await _saved(service))["tokens"]["access_token"] == "access-2"


async def test_a_refused_refresh_waits_for_the_user_to_sign_in_again(service, oauth_server, signed_out, caplog):
    await _add(service)
    await _sign_in(service)
    await _status(service, "connected")
    oauth_server.tokens.clear()
    oauth_server.refuse_refresh = True
    saved = await _saved(service)
    saved["expires_at"] = time.time() - 10
    await secret_store.put(service.store, service.secrets, "mcp:notes", json.dumps(saved))
    caplog.clear()
    await service.mcp.restart("notes")
    server = await _status(service, "needs_sign_in")
    assert "sign in again" in server.error and len(oauth_server.registrations) == 1
    # Stopped at the refusal: the SDK never starts a sign-in, so it logs no traceback.
    assert not [r for r in caplog.records if r.exc_info]
    [alert] = await _alerted(service)
    assert (alert.kind, alert.area, alert.name, alert.failures) == ("signed_out", "mcp", "notes", 0)
    assert signed_out == [{"name": "notes", "error": "notes needs you to sign in again."}]
    await service.mcp.restart("notes")
    await _status(service, "needs_sign_in")
    assert len(signed_out) == 1  # alerted once
    await _sign_in(service, "code-2")
    await _status(service, "connected")
    assert len(oauth_server.registrations) == 1  # the registered client is reused
    assert await service.alerts() == []


async def test_a_lost_sign_in_alert_can_be_dismissed(service, oauth_server):
    await _add(service)
    await _sign_in(service)
    await _status(service, "connected")
    oauth_server.tokens.clear()
    oauth_server.refuse_refresh = True
    saved = await _saved(service)
    saved["expires_at"] = time.time() - 10
    await secret_store.put(service.store, service.secrets, "mcp:notes", json.dumps(saved))
    await service.mcp.restart("notes")
    await _alerted(service)
    await service.dismiss_alert("mcp", "notes")
    assert await service.alerts() == []


async def test_a_refused_code_or_a_used_state_fails_and_keeps_waiting(service, oauth_server):
    await _add(service)
    page = await service.start_mcp_sign_in("notes", REDIRECT)
    state = parse_qs(urlparse(page).query)["state"][0]
    with pytest.raises(SignInError, match="Couldn't sign in to notes"):
        await service.finish_sign_in(state, "bad")
    with pytest.raises(SignInError, match="expired or was already used"):
        await service.finish_sign_in(state, "code-1")
    await _status(service, "needs_sign_in")


async def test_a_newer_sign_in_replaces_the_older_one(service, oauth_server):
    await _add(service)
    old = parse_qs(urlparse(await service.start_mcp_sign_in("notes", REDIRECT)).query)["state"][0]
    await _sign_in(service)
    with pytest.raises(SignInError):
        await service.finish_sign_in(old, "code-1")
    await _status(service, "connected")


async def test_a_server_that_doesnt_ask_or_runs_locally_has_no_sign_in(service, oauth_server):
    oauth_server.open = True
    await service.add_mcp_server(McpServer(name="notes", url=URL))
    await _status(service, "connected")
    with pytest.raises(McpServerError, match="doesn't ask to sign in"):
        await service.start_mcp_sign_in("notes", REDIRECT)
    await service.remove_mcp_server("notes")
    await service.add_mcp_server(McpServer(name="local", command="notes-server"))
    with pytest.raises(McpServerError, match="nothing to sign in to"):
        await service.start_mcp_sign_in("local", REDIRECT)


async def test_the_sign_in_is_forgotten_when_the_server_is_removed_or_moves(service, oauth_server):
    await _add(service)
    await _sign_in(service)
    await _status(service, "connected")
    await service.update_mcp_server("notes", McpServerChanges(url="https://notes.test/mcp?v=2"))
    assert await secret_store.get(service.store, service.secrets, "mcp:notes") == ""
    await _sign_in(service)
    await service.remove_mcp_server("notes")
    assert await secret_store.get(service.store, service.secrets, "mcp:notes") == ""
