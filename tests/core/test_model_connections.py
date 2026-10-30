"""Connections to model providers notice when they died (core/llm/connections.py): TCP keepalive on the
HTTP clients the Copilot, OpenAI-compatible and OpenRouter models use, so a call on a connection that died while the
computer slept fails within a minute of waking, instead of after its 600s read timeout counted awake."""

import asyncio
import json
import socket

import httpx
import pytest
from langchain_core.messages import HumanMessage

from assistant.core.llm import build_llm, connections
from assistant.core.llm.choice import ModelChoice


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


async def test_an_openai_compatible_server_answers_through_them():
    """The SDK takes the client: a reply comes back from a server on this computer."""

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        length = next(
            int(line.split(b":")[1]) for line in head.split(b"\r\n") if line.lower().startswith(b"content-length")
        )
        await reader.readexactly(length)
        body = json.dumps(_completion("Hello.")).encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body) + body
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        choice = ModelChoice("openai", "m", "m", {"api_key": "k", "base_url": f"http://127.0.0.1:{port}/v1"})
        reply = await build_llm(choice, "m").ainvoke([HumanMessage("hi")])
    assert reply.text == "Hello."


def _completion(text: str) -> dict:
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
