"""GitHub Copilot as the model provider (PROVIDER=copilot), with a Copilot subscription's GitHub token.

Copilot doesn't take the GitHub token directly. It's exchanged at GitHub for a Copilot token that
lasts about 30 minutes and names the account's API host. `CopilotAuth` puts the current token on
every request, exchanges a new one shortly before it expires, and retries once with a new one when
the API rejects it. Requests go to Copilot's OpenAI-compatible chat endpoint, including for Claude.

Copilot counts a premium request for each request the user started. The `X-Initiator` header says
which these are: `user` when the request answers a user message, `agent` when it continues after
tool results.
"""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

_EXCHANGE_URL = "https://api.github.com/copilot_internal/v2/token"
DEFAULT_API = "https://api.githubcopilot.com"
# Copilot accepts requests from known editors; these match VS Code's Copilot Chat.
_EDITOR_VERSION = "vscode/1.104.1"
_EXCHANGE_USER_AGENT = "GitHubCopilotChat/0.26.7"
HEADERS = {
    "Editor-Version": _EDITOR_VERSION,
    "Copilot-Integration-Id": "vscode-chat",
    "Openai-Intent": "conversation-edits",
}
# Model calls can stream for minutes; connecting shouldn't take long.
_MODEL_TIMEOUT = httpx.Timeout(600, connect=30)
# A token this close to expiring is replaced before use.
_REFRESH_MARGIN_SECONDS = 120
_TIMEOUT = 20


def chat_model(
    model: str, github_token: str, max_tokens: int, transport: httpx.AsyncBaseTransport | None = None
) -> ChatOpenAI:
    """A chat model on Copilot's OpenAI-compatible endpoint. `transport` replaces the network in tests."""
    tokens = CopilotTokens(github_token, httpx.AsyncClient(transport=transport))
    http = httpx.AsyncClient(transport=transport, auth=CopilotAuth(tokens), headers=HEADERS, timeout=_MODEL_TIMEOUT)
    return ChatOpenAI(
        model=model,
        base_url=DEFAULT_API,
        # Never sent: CopilotAuth sets the Authorization header on each request.
        api_key=SecretStr("set-per-request"),
        http_async_client=http,
        max_completion_tokens=max_tokens,
        output_version="v1",
        # Ask for token usage on streamed replies too (the token ledger, core/usage).
        stream_usage=True,
    )


class CopilotAuthError(Exception):
    """The GitHub token couldn't be exchanged for a Copilot token. The text says why."""


@dataclass(frozen=True)
class CopilotToken:
    value: str
    expires_at: float
    # The account's API host, e.g. https://api.individual.githubcopilot.com.
    api: str

    def fresh(self, now: float) -> bool:
        return now < self.expires_at - _REFRESH_MARGIN_SECONDS


class CopilotTokens:
    """The current Copilot token for a GitHub token, exchanged again when it's about to expire.
    Concurrent model calls share one exchange."""

    def __init__(self, github_token: str, http: httpx.AsyncClient) -> None:
        self._github_token = github_token
        self._http = http
        self._token: CopilotToken | None = None
        self._lock = asyncio.Lock()

    async def current(self) -> CopilotToken:
        async with self._lock:
            if self._token is None or not self._token.fresh(time.time()):
                self._token = await self._exchange()
            return self._token

    def discard(self, token: CopilotToken) -> None:
        """The API rejected `token`: the next call exchanges a new one."""
        if self._token == token:
            self._token = None

    async def _exchange(self) -> CopilotToken:
        if not self._github_token:
            raise CopilotAuthError("COPILOT_GITHUB_TOKEN isn't set.")
        headers = {
            "Authorization": f"token {self._github_token}",
            "Accept": "application/json",
            "Editor-Version": _EDITOR_VERSION,
            "User-Agent": _EXCHANGE_USER_AGENT,
        }
        try:
            response = await self._http.get(_EXCHANGE_URL, headers=headers, timeout=_TIMEOUT)
        except httpx.HTTPError as e:
            raise CopilotAuthError(f"Couldn't reach GitHub to get a Copilot token: {e}") from e
        if response.status_code != 200:
            raise CopilotAuthError(_rejection(response))
        return _token(response.json())


class CopilotAuth(httpx.Auth):
    """Signs each request to the Copilot API, sends it to the account's host, and marks who started it."""

    # The body says who started the request (`initiator`).
    requires_request_body = True

    def __init__(self, tokens: CopilotTokens) -> None:
        self._tokens = tokens

    async def async_auth_flow(self, request: httpx.Request) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await self._tokens.current()
        response = yield _signed(request, token)
        if response.status_code == 401:
            self._tokens.discard(token)
            yield _signed(request, await self._tokens.current())


def initiator(body: bytes) -> str:
    """`user` for a request whose last message is the user's, `agent` after tool results."""
    try:
        messages = json.loads(body).get("messages") or [{}]
    except (ValueError, AttributeError):
        return "agent"
    return "user" if messages[-1].get("role") == "user" else "agent"


def _signed(request: httpx.Request, token: CopilotToken) -> httpx.Request:
    api = httpx.URL(token.api)
    request.url = request.url.copy_with(scheme=api.scheme, host=api.host, port=api.port)
    request.headers["Authorization"] = f"Bearer {token.value}"
    request.headers["X-Initiator"] = initiator(request.content)
    return request


def _token(data: dict) -> CopilotToken:
    value = str(data.get("token") or "")
    if not value:
        raise CopilotAuthError("GitHub answered without a Copilot token.")
    expires_at = float(data.get("expires_at") or time.time() + 1800)
    endpoints = data.get("endpoints")
    api = str((endpoints if isinstance(endpoints, dict) else {}).get("api") or DEFAULT_API).rstrip("/")
    return CopilotToken(value, expires_at, api)


def _rejection(response: httpx.Response) -> str:
    if response.status_code == 401:
        return "GitHub rejected COPILOT_GITHUB_TOKEN: it's wrong or was revoked."
    if response.status_code in (403, 404):
        return "This GitHub account has no Copilot subscription that allows this, or the token lacks access."
    return f"GitHub didn't give a Copilot token (HTTP {response.status_code}): {response.text[:200]}"
