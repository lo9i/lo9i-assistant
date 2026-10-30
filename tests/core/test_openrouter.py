"""The OpenRouter provider: requests to OpenRouter with the key and the headers it credits the app's calls to,
replies streamed with their tool calls and usage, reasoning sent back as it came, structured answers through a
tool call, and the models that take tools listed from its public list with their context windows."""

import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openrouter import ChatOpenRouter
from pydantic import BaseModel

from assistant.core.config import settings
from assistant.core.llm import build_llm, build_structured, choice, connections, openrouter
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.openrouter import OpenRouterError

_KEY = "sk-or-v1-right"
_MODEL = "anthropic/claude-opus-5.5"


class _OpenRouter:
    """A fake OpenRouter API. Streams `chunks` when a reply is streamed, answers `message` otherwise."""

    def __init__(self, message: dict | None = None, chunks: list[dict] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.message = message or {"role": "assistant", "content": "Hi!"}
        self.chunks = chunks or []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if json.loads(request.content).get("stream"):
            events = "".join(f"data: {json.dumps(c)}\n\n" for c in self.chunks) + "data: [DONE]\n\n"
            return httpx.Response(200, text=events, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=_completion(self.message))

    def body(self, n: int = -1) -> dict:
        return json.loads(self.requests[n].content)


def _completion(message: dict) -> dict:
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 0,
        "model": _MODEL,
        "system_fingerprint": None,
        "choices": [
            {"index": 0, "message": message, "finish_reason": "tool_calls" if "tool_calls" in message else "stop"}
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }


def _chunk(delta: dict, finish: str | None = None) -> dict:
    return {
        "id": "gen-1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": _MODEL,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def _usage() -> dict:
    usage = {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
    return {
        "id": "gen-1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": _MODEL,
        "choices": [],
        "usage": usage,
    }


def _thought(text: str, signature: str | None = None) -> dict:
    # OpenRouter repeats the entry's type, format and index in each fragment.
    return {"type": "reasoning.text", "text": text, "signature": signature, "format": "anthropic-claude-v1", "index": 0}


def _call(arguments: str, start: bool = False) -> dict:
    call: dict = {"index": 0, "function": {"arguments": arguments}}
    if start:
        call |= {"id": "call_1", "type": "function", "function": {"name": "add", "arguments": arguments}}
    return {"tool_calls": [call]}


_STREAM = [
    _chunk({"role": "assistant", "content": "", "reasoning": "Add ", "reasoning_details": [_thought("Add ")]}),
    _chunk({"reasoning": "them.", "reasoning_details": [_thought("them.")]}),
    _chunk({"reasoning_details": [_thought("", signature="sig")]}),
    _chunk({"content": "Adding."}),
    _chunk(_call('{"a": 1,', start=True)),
    _chunk(_call(' "b": 2}'), finish="tool_calls"),
    _usage(),
]


@tool
def add(a: int, b: int) -> int:
    """Adds two numbers."""
    return a + b


def _model(fake: _OpenRouter):
    return openrouter.chat_model(_MODEL, _KEY, 1000, transport=httpx.MockTransport(fake.handler))


async def _streamed(model, messages) -> AIMessage:
    whole = None
    async for chunk in model.astream(messages):
        whole = chunk if whole is None else whole + chunk
    assert whole is not None
    return AIMessage(
        content=whole.content,
        tool_calls=whole.tool_calls,
        additional_kwargs=whole.additional_kwargs,
        usage_metadata=whole.usage_metadata,
    )


async def test_requests_go_to_openrouter_with_the_key_and_the_apps_headers():
    fake = _OpenRouter()
    reply = await _model(fake).ainvoke([HumanMessage("hi")])
    assert reply.text == "Hi!"
    request = fake.requests[0]
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {_KEY}"
    assert (request.headers["HTTP-Referer"], request.headers["X-Title"]) == ("https://lo9i.com.ar", "lo9i")
    assert (fake.body()["model"], fake.body()["max_tokens"]) == (_MODEL, 1000)


async def test_a_streamed_reply_brings_its_text_tool_calls_and_usage():
    fake = _OpenRouter(chunks=_STREAM)
    reply = await _streamed(_model(fake).bind_tools([add]), [HumanMessage("1 + 2?")])
    assert reply.text == "Adding."
    assert [(c["name"], c["args"], c["id"]) for c in reply.tool_calls] == [("add", {"a": 1, "b": 2}, "call_1")]
    assert reply.usage_metadata is not None and reply.usage_metadata["input_tokens"] == 5
    body = fake.body()
    assert body["stream"] and body["stream_options"] == {"include_usage": True}
    assert body["tools"][0]["function"]["name"] == "add"


async def test_the_reasoning_goes_back_with_the_tool_results_as_it_came():
    """Some models refuse tool results without the reasoning that asked for them, and a reasoning entry whose
    fragments were joined into a repeated format."""
    fake = _OpenRouter(chunks=_STREAM)
    model = _model(fake).bind_tools([add])
    asked = [SystemMessage("Be brief."), HumanMessage("1 + 2?")]
    reply = await _streamed(model, asked)
    await model.ainvoke([*asked, reply, ToolMessage("3", tool_call_id="call_1")])
    sent = fake.body()["messages"][2]
    assert sent["reasoning_details"] == [
        {"type": "reasoning.text", "text": "Add them.", "signature": "sig", "format": "anthropic-claude-v1", "index": 0}
    ]
    assert sent["reasoning"] == "Add them."
    assert sent["tool_calls"][0]["id"] == "call_1" and json.loads(sent["tool_calls"][0]["function"]["arguments"]) == {
        "a": 1,
        "b": 2,
    }


class Title(BaseModel):
    title: str


async def test_structured_answers_come_through_a_tool_call(monkeypatch):
    call = {"id": "t1", "type": "function", "function": {"name": "Title", "arguments": '{"title": "Rome"}'}}
    fake = _OpenRouter({"role": "assistant", "content": None, "tool_calls": [call]})
    monkeypatch.setattr(connections, "transport", lambda: httpx.MockTransport(fake.handler))
    model = ModelChoice("openrouter", _MODEL, _MODEL, {"api_key": _KEY})
    answer = await build_structured(model, _MODEL, Title).ainvoke([HumanMessage("Title this")])
    assert answer == Title(title="Rome")
    assert fake.body()["tools"][0]["function"]["name"] == "Title"


def _listing(request: httpx.Request) -> httpx.Response:
    assert str(request.url) == "https://openrouter.ai/api/v1/models"
    assert request.headers["X-Title"] == "lo9i"
    models = [
        {"id": "anthropic/claude-opus-5.5", "name": "Anthropic: Claude Opus 5.5", "context_length": 1_000_000,
         "supported_parameters": ["max_tokens", "tools", "tool_choice"]},
        {"id": "some/image-model", "name": "Images", "context_length": 4096, "supported_parameters": ["max_tokens"]},
        {"id": "openai/gpt-6", "context_length": None, "supported_parameters": ["tools"]},
    ]  # fmt: skip
    return httpx.Response(200, json={"data": models})


async def test_the_models_that_take_tools_are_listed_in_openrouters_order():
    listed = await openrouter.list_models(httpx.MockTransport(_listing))
    assert listed == [("anthropic/claude-opus-5.5", "Anthropic: Claude Opus 5.5"), ("openai/gpt-6", "openai/gpt-6")]
    refused = httpx.MockTransport(lambda request: httpx.Response(503))
    with pytest.raises(OpenRouterError, match="503"):
        await openrouter.list_models(refused)


async def test_a_models_context_window_comes_from_openrouters_model_list():
    transport = httpx.MockTransport(_listing)
    assert await openrouter.context_window("anthropic/claude-opus-5.5", transport) == 1_000_000
    assert await openrouter.context_window("openai/gpt-6", transport) is None
    assert await openrouter.context_window("missing/model", transport) is None


async def test_the_app_lists_openrouters_models_without_a_key(service, monkeypatch):
    from assistant.core.agent import ModelOption, ModelSettingsError

    async def list_models(transport=None):
        return [("anthropic/claude-opus-5.5", "Claude Opus 5.5")]

    monkeypatch.setattr(openrouter, "list_models", list_models)
    expected = [ModelOption("anthropic/claude-opus-5.5", "Claude Opus 5.5")]
    assert await service.available_models("openrouter", {}) == expected

    async def unreachable(transport=None):
        raise OpenRouterError("Couldn't reach OpenRouter for its models: no network")

    monkeypatch.setattr(openrouter, "list_models", unreachable)
    with pytest.raises(ModelSettingsError, match="no network"):
        await service.available_models("openrouter", {})


def test_env_settings_choose_openrouter_with_its_key(monkeypatch):
    monkeypatch.setattr(settings, "provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", _KEY)
    monkeypatch.setattr(settings, "model", _MODEL)
    monkeypatch.setattr(settings, "worker_model", "anthropic/claude-sonnet-5.5")
    chosen = choice.from_env()
    assert chosen == ModelChoice("openrouter", _MODEL, "anthropic/claude-sonnet-5.5", {"api_key": _KEY})
    built = build_llm(chosen, chosen.model)
    assert isinstance(built, ChatOpenRouter) and built.model_name == _MODEL


def test_openrouter_is_offered_with_its_key_and_suggested_models(service):
    offered = {p.id: p for p in service.model_providers()}["openrouter"]
    assert offered.installed and [f.key for f in offered.fields] == ["api_key"]
    assert (offered.model, offered.worker_model) == ("anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5")
