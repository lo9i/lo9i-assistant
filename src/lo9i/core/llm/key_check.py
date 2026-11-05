"""Whether the model's key works, with one cheap request that lists models or reads the key, never a model call: the
setup check runs it each time it's asked (core/setup_check/). Only providers with such a request are checked; the
others' keys are checked when a model answers."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import httpx

from lo9i.core.i18n import message
from lo9i.core.llm import copilot
from lo9i.core.llm.choice import ModelChoice

_SECONDS = 15
_ANTHROPIC_MODELS = "https://api.anthropic.com/v1/models?limit=1"
_ANTHROPIC_VERSION = "2023-06-01"
_OPENAI = "https://api.openai.com/v1"
_OPENROUTER_KEY = "https://openrouter.ai/api/v1/key"
_REFUSED = frozenset({401, 403})
# An OpenAI-compatible server that doesn't list its models: nothing says whether the key works.
_NOT_SERVED = frozenset({404, 405})

KeyState = Literal["works", "refused", "unreachable", "unchecked"]


@dataclass(frozen=True)
class KeyVerdict:
    state: KeyState
    # Why it was refused or couldn't be reached; "" otherwise.
    reason: str = ""


Transport = httpx.AsyncBaseTransport | None


async def check(choice: ModelChoice, transport: Transport = None) -> KeyVerdict:
    checker = _CHECKERS.get(choice.provider)
    if checker is None:
        return KeyVerdict("unchecked")
    try:
        async with asyncio.timeout(_SECONDS):
            return await checker(choice.values, transport)
    except (httpx.HTTPError, TimeoutError) as e:
        return KeyVerdict("unreachable", str(e) or type(e).__name__)


async def _anthropic(values: dict[str, str], transport: Transport) -> KeyVerdict:
    headers = {"x-api-key": values.get("api_key", ""), "anthropic-version": _ANTHROPIC_VERSION}
    return _verdict(await _status(_ANTHROPIC_MODELS, headers, transport))


async def _openai(values: dict[str, str], transport: Transport) -> KeyVerdict:
    url = (values.get("base_url") or _OPENAI).rstrip("/") + "/models"
    status = await _status(url, _bearer(values), transport)
    return KeyVerdict("unchecked") if status in _NOT_SERVED else _verdict(status)


async def _openrouter(values: dict[str, str], transport: Transport) -> KeyVerdict:
    return _verdict(await _status(_OPENROUTER_KEY, _bearer(values), transport))


async def _copilot(values: dict[str, str], transport: Transport) -> KeyVerdict:
    try:
        await copilot.list_models(values.get("api_key", ""), transport)
    except copilot.CopilotAuthError as e:
        return KeyVerdict("refused", message(e))
    return KeyVerdict("works")


def _bearer(values: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {values.get('api_key', '')}"}


async def _status(url: str, headers: dict[str, str], transport: Transport) -> int:
    async with httpx.AsyncClient(transport=transport) as http:
        return (await http.get(url, headers=headers, timeout=_SECONDS)).status_code


def _verdict(status: int) -> KeyVerdict:
    if 200 <= status < 300:
        return KeyVerdict("works")
    return KeyVerdict("refused" if status in _REFUSED else "unreachable", f"HTTP {status}")


_CHECKERS: dict[str, Callable[[dict[str, str], Transport], Awaitable[KeyVerdict]]] = {
    "anthropic": _anthropic,
    "copilot": _copilot,
    "openai": _openai,
    "openrouter": _openrouter,
}
