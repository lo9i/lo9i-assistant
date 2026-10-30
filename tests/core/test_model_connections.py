"""Connections to model providers notice when they died (core/llm/connections.py): TCP keepalive on the
HTTP clients the Anthropic, Copilot, OpenAI-compatible and OpenRouter models use, and those LangChain builds that take
a client, so a call on a connection that died while the computer slept fails within a minute of waking, instead of
after its 600s read timeout counted awake."""

import asyncio
import contextlib
import json
import socket
from collections.abc import AsyncIterator

import httpx
import httpx2
import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI

from assistant.core.llm import build_llm, connections
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.claude import KeptAliveChatAnthropic


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
