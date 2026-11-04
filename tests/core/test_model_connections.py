"""Connections to model providers notice when they died (core/llm/connections.py): TCP keepalive on the
HTTP clients the Anthropic, Copilot, OpenAI-compatible and OpenRouter models use, and those LangChain builds whose
package lets them be given (core/llm/kept_alive.py), so a call on a connection that died while the computer slept
fails within a minute of waking, instead of after its 600s read timeout counted awake. The LangChain providers'
packages aren't installed here: their models are stood in for by what they're built with."""

import asyncio
import contextlib
import json
import socket
import sys
import types
from collections.abc import AsyncIterator
from typing import Any

import httpx
import httpx2
import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI
from pydantic import SecretStr

import lo9i.core.llm as llm_module
from lo9i.core.llm import build_llm, connections
from lo9i.core.llm.choice import ModelChoice
from lo9i.core.llm.claude import KeptAliveChatAnthropic


def test_connections_probe_the_provider_once_idle():
    options = {(level, name): value for level, name, value in connections.socket_options()}
    assert options[(socket.SOL_SOCKET, socket.SO_KEEPALIVE)] == 1
    assert options[(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL)] == 10
    assert options[(socket.IPPROTO_TCP, socket.TCP_KEEPCNT)] == 3
    assert 30 in options.values()  # the idle time before the first probe, named per system


@pytest.mark.parametrize("provider", ["copilot", "openai", "openrouter"])
def test_the_models_built_here_use_those_connections(provider, monkeypatch):
    made: list[httpx.AsyncHTTPTransport] = []

    def transport() -> httpx.AsyncHTTPTransport:
        made.append(httpx.AsyncHTTPTransport(socket_options=connections.socket_options()))
        return made[-1]

    monkeypatch.setattr(connections, "transport", transport)
    build_llm(ModelChoice(provider, "m", "m", {"api_key": "k"}), "m")
    assert made


def test_a_langchain_model_that_takes_a_client_gets_them(monkeypatch):
    made: list[httpx.AsyncClient] = []
    monkeypatch.setattr(connections, "client", lambda: made.append(httpx.AsyncClient()) or made[-1])
    values = {"azure_endpoint": "https://r.openai.azure.com/", "api_key": "k", "api_version": "2024-10-21"}
    model = build_llm(ModelChoice("azure_openai", "gpt-4o", "gpt-4o", values), "gpt-4o")
    assert isinstance(model, AzureChatOpenAI) and made and model.http_async_client is made[0]


class _Model:
    """Stands in for a LangChain model: what init_chat_model was given, and the fields it filled itself."""

    def __init__(self, **fields: Any) -> None:
        self.given: dict[str, Any] = {}
        self.__dict__.update(fields)


def _built(monkeypatch, provider: str, **fields: Any) -> Any:
    model = _Model(**fields)
    monkeypatch.setattr(llm_module, "init_chat_model", lambda name, **given: model.given.update(given) or model)
    assert build_llm(ModelChoice(provider, "m", "m", {"api_key": "k"}), "m") is model
    return model


def _on_them(transport: Any) -> bool:
    return transport._pool._socket_options == connections.socket_options()


def _sdk(monkeypatch, name: str, client: str, made: Any) -> dict[str, Any]:
    """A stand-in for the SDK module `name`, whose `client` records what it's made with and returns `made`."""
    given: dict[str, Any] = {}
    module = types.ModuleType(name)
    setattr(module, client, lambda **kwargs: given.update(kwargs) or made)
    monkeypatch.setitem(sys.modules, name, module)
    return given


@pytest.mark.parametrize("provider", ["azure_ai", "bedrock_mantle_openai", "langsmith"])
def test_the_other_models_on_the_openai_sdk_take_a_client_on_them(provider, monkeypatch):
    assert _on_them(_built(monkeypatch, provider).given["http_async_client"]._transport)


def test_ollama_and_claude_on_vertex_take_them_as_arguments(monkeypatch):
    assert _on_them(_built(monkeypatch, "ollama").given["async_client_kwargs"]["transport"])
    assert _on_them(_built(monkeypatch, "google_anthropic_vertex").given["async_http_client"]._transport)


def test_mistrals_client_is_made_again_on_them_with_its_address_key_and_timeout(monkeypatch):
    made = httpx.AsyncClient(base_url="https://api.mistral.ai/v1", headers={"Authorization": "Bearer k"}, timeout=120)
    again = _built(monkeypatch, "mistralai", async_client=made).async_client
    assert again is not made and _on_them(again._transport)
    assert (again.base_url, again.headers["authorization"], again.timeout) == (made.base_url, "Bearer k", made.timeout)


def test_perplexitys_client_is_copied_onto_them(monkeypatch):
    copied: list[httpx.AsyncClient] = []
    made = types.SimpleNamespace(copy=lambda http_client: copied.append(http_client) or "copy")
    assert _built(monkeypatch, "perplexity", async_client=made).async_client == "copy"
    assert _on_them(copied[0]._transport)


def test_fireworks_client_is_made_again_on_them_without_retries(monkeypatch):
    made = types.SimpleNamespace(chat=types.SimpleNamespace(completions="completions"))
    given = _sdk(monkeypatch, "fireworks", "AsyncFireworks", made)
    fields = {"fireworks_api_key": SecretStr("k"), "fireworks_api_base": None, "async_client": "theirs"}
    assert _built(monkeypatch, "fireworks", **fields).async_client == "completions"
    assert (given["api_key"], given["base_url"], given["max_retries"]) == ("k", None, 0)
    assert _on_them(given["http_client"]._transport)


def test_cohere_client_is_made_again_on_them_from_its_settings(monkeypatch):
    given = _sdk(monkeypatch, "cohere", "AsyncClient", "again")
    fields = {"cohere_api_key": SecretStr("k"), "user_agent": "lc", "timeout_seconds": 300, "base_url": None}
    assert _built(monkeypatch, "cohere", async_client="theirs", **fields).async_client == "again"
    assert (given["api_key"], given["client_name"], given["timeout"]) == ("k", "lc", 300)
    assert _on_them(given["httpx_client"]._transport)


def test_anthropics_sdk_client_is_on_them(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    model = build_llm(ModelChoice("anthropic", "m", "m"), "m")
    assert isinstance(model, KeptAliveChatAnthropic)
    transport = model._async_client._client._transport
    assert isinstance(transport, httpx2.AsyncHTTPTransport)
    assert transport._pool._socket_options == connections.socket_options()


async def test_an_anthropic_server_answers_through_them(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    async with _serving(_message("Hello.")) as port:
        monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{port}")
        reply = await build_llm(ModelChoice("anthropic", "m", "m"), "m").ainvoke([HumanMessage("hi")])
    assert reply.text == "Hello."


async def test_an_openai_compatible_server_answers_through_them():
    """The SDK takes the client: a reply comes back from a server on this computer."""
    async with _serving(_completion("Hello.")) as port:
        choice = ModelChoice("openai", "m", "m", {"api_key": "k", "base_url": f"http://127.0.0.1:{port}/v1"})
        reply = await build_llm(choice, "m").ainvoke([HumanMessage("hi")])
    assert reply.text == "Hello."


@contextlib.asynccontextmanager
async def _serving(answer: dict) -> AsyncIterator[int]:
    """A server on this computer that answers every request with `answer`; yields its port."""

    async def respond(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        length = next(
            int(line.split(b":")[1]) for line in head.split(b"\r\n") if line.lower().startswith(b"content-length")
        )
        await reader.readexactly(length)
        body = json.dumps(answer).encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body) + body
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(respond, "127.0.0.1", 0)
    async with server:
        yield server.sockets[0].getsockname()[1]


def _completion(text: str) -> dict:
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _message(text: str) -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "m",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
