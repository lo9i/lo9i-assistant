"""What the model providers receive: caching, fallbacks and provider-neutral messages."""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from assistant.core.llm import build_llm
from assistant.core.llm.choice import ModelChoice


def test_anthropic_requests_enable_caching_and_fallbacks(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    payload = _anthropic()._get_request_payload([SystemMessage("s"), HumanMessage("hi")])
    assert payload["cache_control"] == {"type": "ephemeral"}
    assert payload["fallbacks"] == "default" and payload["betas"] == ["server-side-fallback-2026-07-01"]


def _history():
    ai = AIMessage(
        content=[
            {"type": "reasoning", "reasoning": "", "extras": {"signature": "SIG"}},
            {"type": "text", "text": "Let me check."},
            {"type": "tool_call", "id": "t1", "name": "bash", "args": {"command": "ls"}},
        ],
        tool_calls=[{"id": "t1", "name": "bash", "args": {"command": "ls"}}],
        response_metadata={"model_provider": "anthropic", "output_version": "v1"},
    )
    return [HumanMessage(content=[{"type": "text", "text": "hi"}]), ai, ToolMessage("f.txt", tool_call_id="t1")]


def test_stored_messages_convert_for_anthropic_keeping_the_thinking_signature(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assistant = _anthropic()._get_request_payload(_history())["messages"][1]
    assert assistant["content"][0] == {"thinking": "", "type": "thinking", "signature": "SIG"}


def test_stored_messages_convert_for_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assistant = _openai()._get_request_payload(_history())["messages"][1]
    assert assistant["tool_calls"][0]["function"]["name"] == "bash"
    assert assistant["content"] == [{"type": "text", "text": "Let me check."}]


def _anthropic() -> ChatAnthropic:
    model = build_llm(ModelChoice("anthropic", "", "", "claude-opus-5-5", "claude-opus-5-5"), "claude-opus-5-5")
    assert isinstance(model, ChatAnthropic)
    return model


def _openai() -> ChatOpenAI:
    model = build_llm(ModelChoice("openai", "", "", "gpt-test", "gpt-test"), "gpt-test")
    assert isinstance(model, ChatOpenAI)
    return model
