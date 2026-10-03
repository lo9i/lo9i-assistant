"""The Copilot provider: GitHub token exchanged for a Copilot token, requests signed and sent to the
account's host, who started each request, a retry on a rejected token, and structured answers."""

import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from assistant.core.llm import build_structured, copilot
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.copilot import CopilotAuthError, CopilotTokens

_EXCHANGE = "https://api.github.com/copilot_internal/v2/token"
_HOST = "api.business.githubcopilot.com"


class _Copilot:
    """Fake GitHub and Copilot APIs. `reject_next` makes the next chat request a 401."""

    def __init__(self, answer: dict | None = None) -> None:
        self.exchanges = 0
        self.requests: list[httpx.Request] = []
        self.reject_next = False
        self.answer = answer or {"role": "assistant", "content": "Hi!"}

    def handler(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == _EXCHANGE:
            return self._exchange(request)
        # A copy: a retry sends the same request object again with new headers.
        self.requests.append(
            httpx.Request(request.method, request.url, headers=request.headers, content=request.content)
        )
        if self.reject_next:
            self.reject_next = False
            return httpx.Response(401, json={"error": {"message": "expired"}})
        return httpx.Response(200, json=_completion(self.answer))

    def _exchange(self, request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] != "token gh-right":
            return httpx.Response(401, json={"message": "Bad credentials"})
        self.exchanges += 1
        token = f"copilot-{self.exchanges}"
        return httpx.Response(
            200, json={"token": token, "expires_at": 4102444800, "endpoints": {"api": f"https://{_HOST}"}}
        )


def _completion(message: dict) -> dict:
    finish = "tool_calls" if message.get("tool_calls") else "stop"
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "claude-opus-5.5",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }


def _model(fake: _Copilot, token: str = "gh-right"):
    return copilot.chat_model("claude-opus-5.5", token, 1000, transport=httpx.MockTransport(fake.handler))


async def test_requests_go_signed_to_the_accounts_host():
    fake = _Copilot()
    reply = await _model(fake).ainvoke([HumanMessage("hi")])
    assert reply.text == "Hi!"
    request = fake.requests[0]
    assert request.url.host == _HOST and request.url.path == "/chat/completions"
    assert request.headers["Authorization"] == "Bearer copilot-1"
    assert request.headers["Copilot-Integration-Id"] == "vscode-chat" and request.headers["X-Initiator"] == "user"
    assert json.loads(request.content)["max_completion_tokens"] == 1000


async def test_a_request_after_tool_results_is_the_agents_and_reuses_the_token():
    fake = _Copilot()
    model = _model(fake)
    call = AIMessage("", tool_calls=[{"id": "t1", "name": "bash", "args": {"command": "ls"}}])
    await model.ainvoke([HumanMessage("list"), call, ToolMessage("f.txt", tool_call_id="t1")])
    await model.ainvoke([HumanMessage("again")])
    assert [r.headers["X-Initiator"] for r in fake.requests] == ["agent", "user"]
    assert fake.exchanges == 1


async def test_a_rejected_token_is_exchanged_again_and_the_request_retried():
    fake = _Copilot()
    fake.reject_next = True
    reply = await _model(fake).ainvoke([HumanMessage("hi")])
    assert reply.text == "Hi!" and fake.exchanges == 2
    assert [r.headers["Authorization"] for r in fake.requests] == ["Bearer copilot-1", "Bearer copilot-2"]


async def test_a_wrong_github_token_says_so():
    fake = _Copilot()
    tokens = CopilotTokens("gh-wrong", httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
    with pytest.raises(CopilotAuthError, match="rejected COPILOT_GITHUB_TOKEN"):
        await tokens.current()
    with pytest.raises(CopilotAuthError, match="isn't set"):
        await CopilotTokens("", httpx.AsyncClient()).current()


class Title(BaseModel):
    title: str


async def test_structured_answers_come_through_a_tool_call_on_copilot(monkeypatch):
    fake = _Copilot(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "Title", "arguments": '{"title": "Rome"}'}}
            ],
        }
    )
    real = copilot.chat_model
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr(
        copilot, "chat_model", lambda model, token, max_tokens: real(model, "gh-right", 1000, transport)
    )
    model = ModelChoice("copilot", "claude-opus-5.5", "claude-sonnet-5.5", {"api_key": "gh-right"})
    answer = await build_structured(model, "claude-opus-5.5", Title).ainvoke([HumanMessage("Title this")])
    assert answer == Title(title="Rome")
    body = json.loads(fake.requests[0].content)
    assert body["tool_choice"] == "auto" and "response_format" not in body
    assert body["messages"][-1]["content"] == "Answer only by calling the Title tool."
