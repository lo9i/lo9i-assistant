"""GitHub Copilot as the model provider (PROVIDER=copilot), with a Copilot subscription's GitHub token.

Copilot doesn't take the GitHub token directly. It's exchanged at GitHub for a Copilot token that
lasts about 30 minutes and names the account's API host. `CopilotAuth` puts the current token on
every request, exchanges a new one shortly before it expires, and retries once with a new one when
the API rejects it. Requests go to Copilot's OpenAI-compatible chat endpoint, including for Claude.

Copilot ignores an assistant message whose content is a list of parts (as LangChain sends the replies
it keeps, `output_version="v1"`): the model then reads the conversation without its own replies. Its
text goes as a string instead (`_CopilotChat`).

Copilot counts a premium request for each request the user started. The `X-Initiator` header says
which these are: `user` when the request answers a user message, `agent` when it continues after
tool results.
"""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from assistant.core.attachments import TOOL_MEDIA_SENDER
from assistant.core.llm import connections

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
# A token this close to expiring is replaced before use.
_REFRESH_MARGIN_SECONDS = 120
_TIMEOUT = 20


def chat_model(
    model: str, github_token: str, max_tokens: int, transport: httpx.AsyncBaseTransport | None = None
) -> ChatOpenAI:
    """A chat model on Copilot's OpenAI-compatible endpoint, on connections that notice when they died
    (core/llm/connections.py). `transport` replaces the network in tests."""
    tokens = CopilotTokens(github_token, httpx.AsyncClient(transport=transport or connections.transport()))
    http = httpx.AsyncClient(
        transport=transport or connections.transport(),
        auth=CopilotAuth(tokens),
        headers=HEADERS,
        timeout=connections.MODEL_TIMEOUT,
    )
    return _CopilotChat(
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


async def list_models(github_token: str, transport: httpx.AsyncBaseTransport | None = None) -> list[tuple[str, str]]:
    """The chat models this account can pick, as (id, name), in Copilot's order. Raises
    CopilotAuthError when the token is refused or Copilot can't be reached."""
    models = await _models(github_token, transport)
    return [(str(m["id"]), str(m.get("name") or m["id"])) for m in models if _pickable(m)]


async def context_window(
    github_token: str, model: str, transport: httpx.AsyncBaseTransport | None = None
) -> int | None:
    """How many tokens `model` takes in, as Copilot's model list says; None when it doesn't. Raises
    CopilotAuthError as list_models does."""
    found = next((m for m in await _models(github_token, transport) if m.get("id") == model), None)
    limits = ((found or {}).get("capabilities") or {}).get("limits") or {}
    tokens = limits.get("max_context_window_tokens") or limits.get("max_prompt_tokens")
    return int(tokens) if tokens else None


async def _models(github_token: str, transport: httpx.AsyncBaseTransport | None) -> list[dict]:
    tokens = CopilotTokens(github_token, httpx.AsyncClient(transport=transport))
    async with httpx.AsyncClient(transport=transport, auth=CopilotAuth(tokens), headers=HEADERS) as http:
        try:
            response = await http.get(f"{DEFAULT_API}/models", timeout=_TIMEOUT)
        except httpx.HTTPError as e:
            raise CopilotAuthError(f"Couldn't reach Copilot for its models: {e}") from e
    if response.status_code != 200:
        raise CopilotAuthError(f"Copilot didn't list its models ({response.status_code}).")
    return list(response.json().get("data", []))


def _pickable(model: dict) -> bool:
    """A chat model the account may pick, as Copilot's own model picker shows it."""
    capabilities = model.get("capabilities") or {}
    return bool(model.get("id")) and capabilities.get("type") == "chat" and model.get("model_picker_enabled", True)


class _CopilotChat(ChatOpenAI):
    def _get_request_payload(self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        for message in payload.get("messages", []):
            if message.get("role") == "assistant" and isinstance(message.get("content"), list):
                message["content"] = _text(message["content"])
        return payload


def _text(parts: list[Any]) -> str:
    """The text of an assistant message's parts, as one string."""
    return "".join(p["text"] for p in parts if isinstance(p, dict) and p.get("type") == "text")


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
    """`user` for a request whose last message is the user's, `agent` after tool results, including
    the user message that only carries the results' images."""
    try:
        messages = json.loads(body).get("messages") or [{}]
    except (ValueError, AttributeError):
        return "agent"
    last = messages[-1]
    return "user" if last.get("role") == "user" and last.get("name") != TOOL_MEDIA_SENDER else "agent"


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
