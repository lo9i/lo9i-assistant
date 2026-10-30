"""Signing in to remote MCP servers with OAuth, as the MCP authorization spec asks.

The SDK's OAuthClientProvider does the protocol: it finds the server's authorization server, registers
this assistant there as a client (dynamic client registration), and runs the authorization code flow
with PKCE and the refreshes. This module keeps what it learns, one secret per server
(core/secret_store.py): the registered client, the tokens, when the access token expires and the
authorization server's metadata, so a new connection refreshes at the right endpoint without
discovering it again.

A connection never waits for the user: when the server asks to sign in and there's no sign-in, or it
can't be refreshed, the connection fails with SignInNeededError until the user signs in from the app.
"""

import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

import httpx2
from langgraph.store.base import BaseStore
from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthMetadata,
    OAuthToken,
    ProtectedResourceMetadata,
)
from pydantic import AnyUrl, BaseModel, ValidationError

from assistant.core import secret_store
from assistant.core.i18n import said
from assistant.core.mcp.servers import McpServer
from assistant.core.secret_store import SecretBox, SecretError

_CLIENT_NAME = "lo9i"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

ShowPage = Callable[[str], Awaitable[None]]
WaitForCode = Callable[[], Awaitable[AuthorizationCodeResult]]


class SignInNeededError(Exception):
    """The server wants a sign-in the assistant doesn't have, or one that stopped working (`lost`)."""

    def __init__(self, message: str, lost: bool = False) -> None:
        super().__init__(message)
        self.lost = lost


def needs_sign_in(error: BaseException) -> SignInNeededError | None:
    """The SignInNeededError behind an error, which the SDK may wrap in exception groups."""
    if isinstance(error, SignInNeededError):
        return error
    if isinstance(error, BaseExceptionGroup):
        return next((found for e in error.exceptions if (found := needs_sign_in(e))), None)
    return None


class _Record(BaseModel):
    """A server's sign-in, kept as its secret."""

    client: OAuthClientInformationFull | None = None
    tokens: OAuthToken | None = None
    expires_at: float | None = None
    metadata: OAuthMetadata | None = None
    resource: ProtectedResourceMetadata | None = None


class _Records:
    def __init__(self, store: BaseStore, box: SecretBox, name: str) -> None:
        self._store = store
        self._box = box
        self._ref = f"mcp:{name}"

    async def load(self) -> _Record:
        """Empty when there's none or it can't be read: the user signs in again."""
        try:
            text = await secret_store.get(self._store, self._box, self._ref)
            return _Record.model_validate_json(text) if text else _Record()
        except (SecretError, ValidationError):
            return _Record()

    async def save(self, record: _Record) -> None:
        await secret_store.put(self._store, self._box, self._ref, record.model_dump_json(exclude_none=True))

    async def delete(self) -> None:
        await secret_store.delete(self._store, self._ref)


class _Storage:
    """The SDK's TokenStorage over a server's record."""

    def __init__(self, records: _Records) -> None:
        self._records = records

    async def get_tokens(self) -> OAuthToken | None:
        return (await self._records.load()).tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return (await self._records.load()).client

    async def set_tokens(self, tokens: OAuthToken) -> None:
        record = await self._records.load()
        record.tokens = tokens
        record.expires_at = time.time() + tokens.expires_in if tokens.expires_in else None
        await self._records.save(record)

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        record = await self._records.load()
        record.client = client_info
        await self._records.save(record)


class _SignInStorage(_Storage):
    """Starts without tokens, so the server asks to sign in, and registers the client again when it
    was registered for another redirect URI (the terminal app's localhost, the web app's address)."""

    def __init__(self, records: _Records, redirect_uri: str) -> None:
        super().__init__(records)
        self._redirect_uri = redirect_uri

    async def get_tokens(self) -> OAuthToken | None:
        return None

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        client = await super().get_client_info()
        registered = {str(uri) for uri in (client.redirect_uris or [])} if client else set()
        return client if self._redirect_uri in registered else None


class McpAuth:
    """Remote MCP servers' sign-ins, and the httpx auth that uses them."""

    def __init__(self, store: BaseStore, box: SecretBox) -> None:
        self._store = store
        self._box = box

    def for_connection(self, server: McpServer) -> httpx2.Auth | None:
        """Signs with the saved sign-in and refreshes it; never starts one. None for a local server."""
        return _ConnectionAuth(server, self._records(server.name)) if server.url else None

    def for_sign_in(
        self, server: McpServer, redirect_uri: str, show_page: ShowPage, wait_for_code: WaitForCode
    ) -> OAuthClientProvider:
        """Signs in from the start: `show_page` gets the authorization page, `wait_for_code` returns
        the code the browser brought back to `redirect_uri`."""
        storage = _SignInStorage(self._records(server.name), redirect_uri)
        return OAuthClientProvider(server.url, _client_metadata(redirect_uri), storage, show_page, wait_for_code)

    async def remember(self, name: str, provider: OAuthClientProvider) -> None:
        """Keep the authorization server's metadata a sign-in found, for refreshing later."""
        records = self._records(name)
        record = await records.load()
        record.metadata = provider.context.oauth_metadata
        record.resource = provider.context.protected_resource_metadata
        await records.save(record)

    async def forget(self, name: str) -> None:
        """Drop a server's sign-in: it was removed, or its URL changed."""
        await self._records(name).delete()

    def _records(self, name: str) -> _Records:
        return _Records(self._store, self._box, name)


class _ConnectionAuth(httpx2.Auth):
    """Without a saved sign-in, a 401 means the server asks for one. With one, the SDK's provider
    signs the requests and refreshes the token. A request still refused after that (the refresh was
    refused, the sign-in revoked) raises SignInNeededError before the response reaches the provider:
    the provider would start a sign-in, which a connection can't finish."""

    requires_response_body = True

    def __init__(self, server: McpServer, records: _Records) -> None:
        self._server = server
        self._records = records
        self._provider: OAuthClientProvider | None = None
        self._loaded = False

    async def async_auth_flow(self, request: httpx2.Request) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        provider = await self._signed_in()
        if provider is None:
            response = yield request
            if _asks_to_sign_in(response):
                raise SignInNeededError(said("{name} asks you to sign in.", name=self._server.name))
            return
        flow = provider.async_auth_flow(request)
        outgoing = await flow.__anext__()
        while True:
            response = yield outgoing
            if outgoing is request and _asks_to_sign_in(response):
                await flow.aclose()
                raise SignInNeededError(said("{name} needs you to sign in again.", name=self._server.name), lost=True)
            try:
                outgoing = await flow.asend(response)
            except StopAsyncIteration:
                return

    async def _signed_in(self) -> OAuthClientProvider | None:
        if not self._loaded:
            self._provider = _restored(self._server, await self._records.load(), self._records)
            self._loaded = True
        return self._provider


def _restored(server: McpServer, record: _Record, records: _Records) -> OAuthClientProvider | None:
    """A provider that starts where the saved sign-in left off. The SDK keeps the token's expiry and
    the endpoints only in memory, so they are put back in its context."""
    if record.tokens is None or record.client is None or not record.client.redirect_uris:
        return None
    metadata = _client_metadata(str(record.client.redirect_uris[0]))
    refused = _refusal(server.name)
    provider = OAuthClientProvider(server.url, metadata, _Storage(records), refused, refused)
    context = provider.context
    context.current_tokens, context.client_info = record.tokens, record.client
    context.token_expiry_time = record.expires_at
    context.oauth_metadata, context.protected_resource_metadata = record.metadata, record.resource
    return provider


def _asks_to_sign_in(response: httpx2.Response) -> bool:
    """Not signed in (401), or signed in without a scope the request needs (403 insufficient_scope)."""
    challenge = response.headers.get("www-authenticate", "")
    return response.status_code == 401 or (response.status_code == 403 and "insufficient_scope" in challenge)


def _refusal(name: str) -> Callable[..., Awaitable[Any]]:
    """Stands in for both sign-in steps (showing the page, waiting for the code). `_ConnectionAuth`
    stops a connection before the SDK starts a sign-in, so these are only a guard."""

    async def refuse(*_: object) -> Any:
        raise SignInNeededError(said("{name} needs you to sign in again.", name=name), lost=True)

    return refuse


def _client_metadata(redirect_uri: str) -> OAuthClientMetadata:
    local = urlparse(redirect_uri).hostname in _LOCAL_HOSTS
    return OAuthClientMetadata(
        redirect_uris=[AnyUrl(redirect_uri)],
        client_name=_CLIENT_NAME,
        application_type="native" if local else "web",
    )
