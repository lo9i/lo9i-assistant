"""OpenRouter (https://openrouter.ai): many providers' models through one key, each named by its OpenRouter id,
like anthropic/claude-opus-5.5.

Its API speaks OpenAI's, but the model is LangChain's ChatOpenRouter rather than ChatOpenAI: a reply's reasoning
comes in `reasoning_details`, which ChatOpenAI drops, and some models need it sent back with the tool results that
follow. Its SDK gets connections that notice when they died (core/llm/connections.py) and the headers OpenRouter
credits the app's calls to (https://openrouter.ai/docs/app-attribution)."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_openrouter import ChatOpenRouter
from openrouter import OpenRouter
from openrouter.utils import BackoffStrategy, RetryConfig
from pydantic import SecretStr

from assistant.core.i18n import said
from assistant.core.llm import connections

API = "https://openrouter.ai/api/v1"
HEADERS = {"HTTP-Referer": "https://lo9i.com.ar", "X-Title": "lo9i"}
_TIMEOUT = 30
# As connections.MODEL_TIMEOUT: the SDK sends each request its own timeout, so the client's would never apply.
_MODEL_TIMEOUT_MS = 600_000
# ChatOpenRouter's own retries: up to about five minutes of backoff, connection errors included.
_RETRIES = RetryConfig("backoff", BackoffStrategy(500, 60_000, 1.5, 300_000), retry_connection_errors=True)
# The agent calls tools; a model that can't take them can't be the assistant's.
_TOOLS = "tools"
# What a streamed reasoning fragment says about the entry it belongs to, the same in each of its fragments.
_ENTRY_FIELDS = ("format",)


class OpenRouterError(Exception):
    """OpenRouter didn't list its models. The text says why."""


def chat_model(
    model: str, api_key: str, max_tokens: int, transport: httpx.AsyncBaseTransport | None = None
) -> ChatOpenRouter:
    """A chat model on OpenRouter. `transport` replaces the network in tests."""
    sdk = OpenRouter(
        api_key=api_key,
        async_client=httpx.AsyncClient(
            transport=transport or connections.transport(), headers=HEADERS, follow_redirects=True
        ),
        retry_config=_RETRIES,
        timeout_ms=_MODEL_TIMEOUT_MS,
    )
    return _ChatOpenRouter(
        model=model, api_key=SecretStr(api_key), client=sdk, max_tokens=max_tokens, output_version="v1"
    )


class _ChatOpenRouter(ChatOpenRouter):
    """Sends a streamed reply's reasoning back as it came. LangChain adds a reply's chunks up, merging the
    `reasoning_details` fragments of one entry (same `index`) by joining their strings: the text is whole, but a
    `format` each fragment repeats would go back repeated, and the model would refuse the reasoning. So it's kept
    on an entry's first fragment only."""

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        described: set[tuple[Any, Any, str]] = set()
        async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
            yield _once(chunk, described)


def _once(chunk: ChatGenerationChunk, described: set[tuple[Any, Any, str]]) -> ChatGenerationChunk:
    """The chunk, without the entry fields an earlier fragment of its entry gave."""
    details = chunk.message.additional_kwargs.get("reasoning_details")
    if not details:
        return chunk
    fragments = [_new_fields(fragment, described) for fragment in details]
    message = chunk.message.model_copy(
        update={"additional_kwargs": {**chunk.message.additional_kwargs, "reasoning_details": fragments}}
    )
    return ChatGenerationChunk(message=message, generation_info=chunk.generation_info)


def _new_fields(fragment: Any, described: set[tuple[Any, Any, str]]) -> Any:
    if not isinstance(fragment, dict) or fragment.get("index") is None:
        return fragment  # Merged as a whole entry, not by index.
    entry = (fragment.get("type"), fragment["index"])
    given = {f for f in _ENTRY_FIELDS if f in fragment and (*entry, f) in described}
    described.update((*entry, f) for f in _ENTRY_FIELDS if f in fragment)
    return {k: v for k, v in fragment.items() if k not in given}


async def list_models(transport: httpx.AsyncBaseTransport | None = None) -> list[tuple[str, str]]:
    """The models that take tools, as (id, name), in OpenRouter's order (newest first). The list is public, so it
    needs no key (and doesn't check one). Raises OpenRouterError."""
    return [(m["id"], m.get("name") or m["id"]) for m in await _models(transport) if _takes_tools(m)]


async def context_window(model: str, transport: httpx.AsyncBaseTransport | None = None) -> int | None:
    """How many tokens `model` takes in, as OpenRouter's model list says; None when it doesn't. Raises
    OpenRouterError as list_models does."""
    found = next((m for m in await _models(transport) if m["id"] == model), None)
    return (found or {}).get("context_length") or None


def _takes_tools(model: dict) -> bool:
    return _TOOLS in (model.get("supported_parameters") or [])


async def _models(transport: httpx.AsyncBaseTransport | None) -> list[dict]:
    async with httpx.AsyncClient(transport=transport, headers=HEADERS) as http:
        try:
            response = await http.get(f"{API}/models", timeout=_TIMEOUT)
        except httpx.HTTPError as e:
            raise OpenRouterError(said("Couldn't reach OpenRouter for its models: {error}", error=e)) from e
    if response.status_code != 200:
        raise OpenRouterError(
            said("OpenRouter didn't list its models ({status_code}).", status_code=response.status_code)
        )
    return response.json().get("data", [])
