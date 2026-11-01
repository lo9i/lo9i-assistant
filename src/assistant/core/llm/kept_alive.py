"""The LangChain providers that make their HTTP clients themselves, on connections that notice when they died
(connections.py), where their package lets them be given: a keyword argument the model takes (`options`), or, for
a model that takes its client only as a field it otherwise fills from its own settings, that client made again from
them on those connections once the model is built (`reconnect`).

Left as their packages make them, since only private code reaches their clients: Anthropic on Bedrock and on
Bedrock Mantle (langchain-aws makes them in private properties, and pins Mantle's sign-in on after; the Anthropic
SDK probes idle connections after 60s itself, but on Linux only), NVIDIA (an aiohttp session per call, made by a
private client), Google Gemini (its `client_args` go to the sync client too, and to no client once aiohttp is
installed), Vertex AI (the gRPC channels of its prediction clients), IBM watsonx (its own retrying transport) and
LiteLLM (each provider's SDK, on clients it keeps itself). Bedrock and Bedrock Converse need nothing: botocore's
60s read timeout already fails a dead connection within a minute awake, which its `tcp_keepalive`, with the
system's two-hour idle time, wouldn't change."""

import importlib
from collections.abc import Callable
from typing import Any

import httpx
from langchain_core.language_models import BaseChatModel

from assistant.core.llm import connections

# Built on the OpenAI SDK or Groq's, whose LangChain model takes an httpx client as `http_async_client`.
_OPENAI_SDK = (
    "azure_openai",
    "azure_ai",
    "bedrock_mantle_openai",
    "langsmith",
    "deepseek",
    "xai",
    "groq",
    "together",
    "upstage",
    "baseten",
    "meta",
)

_OPTIONS: dict[str, Callable[[], dict[str, Any]]] = {
    **dict.fromkeys(_OPENAI_SDK, lambda: {"http_async_client": connections.client()}),
    # Passed on to its httpx client.
    "ollama": lambda: {"async_client_kwargs": {"transport": connections.transport()}},
    # The Anthropic SDK's, on httpx2.
    "google_anthropic_vertex": lambda: {"async_http_client": connections.httpx2_client()},
}


def options(provider_id: str) -> dict[str, Any]:
    """The keyword arguments that put the provider's model on those connections; none when it takes none."""
    made = _OPTIONS.get(provider_id)
    return made() if made else {}


def reconnect(provider_id: str, llm: BaseChatModel) -> None:
    """Puts the async client `llm` made on those connections, for the providers whose model takes one only as a
    field: the key, address and timeout it was given are in the client it made from them."""
    if again := _AGAIN.get(provider_id):
        again(llm)


def _mistral(llm: Any) -> None:
    made: httpx.AsyncClient = llm.async_client
    llm.async_client = httpx.AsyncClient(
        base_url=made.base_url, headers=made.headers, timeout=made.timeout, transport=connections.transport()
    )


def _perplexity(llm: Any) -> None:
    llm.async_client = llm.async_client.copy(http_client=connections.client())


def _fireworks(llm: Any) -> None:
    """Its field holds the SDK client's completions, not the client. Without retries, as langchain-fireworks makes
    it: the model retries itself."""
    sdk = importlib.import_module("fireworks")
    client = sdk.AsyncFireworks(
        api_key=llm.fireworks_api_key.get_secret_value() or None,
        base_url=llm.fireworks_api_base,
        max_retries=0,
        http_client=connections.client(),
    )
    llm.async_client = client.chat.completions


def _cohere(llm: Any) -> None:
    sdk = importlib.import_module("cohere")
    key = llm.cohere_api_key
    llm.async_client = sdk.AsyncClient(
        api_key=key.get_secret_value() if key else None,
        client_name=llm.user_agent,
        timeout=llm.timeout_seconds,
        base_url=llm.base_url,
        httpx_client=connections.client(),
    )


_AGAIN: dict[str, Callable[[Any], None]] = {
    "mistralai": _mistral,
    "perplexity": _perplexity,
    "fireworks": _fireworks,
    "cohere": _cohere,
}
