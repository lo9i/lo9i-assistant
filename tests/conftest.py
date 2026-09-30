"""Shared fixtures. Every test runs on temporary data paths with a scripted fake model, so the
suite never touches ~/.lo9i, never calls a real model, and runs offline (except `-m live`)."""

from collections import deque
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import Field

import assistant.core.agent.service as service_module
import assistant.core.graph as graph_module
from assistant.core.agent import AssistantService
from assistant.core.config import settings
from assistant.core.conversation.digest import DigestInput, EpochDigest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name, value in {
        "database_path": tmp_path / "lo9i.db",
        "uploads_dir": tmp_path / "uploads",
        "workspace_dir": tmp_path / "workspace",
        "persona_path": tmp_path / "SOUL.md",
        "daemon_socket": tmp_path / "daemon.sock",
    }.items():
        monkeypatch.setattr(settings, name, str(value))
    # Defaults, whatever the developer's .env says.
    monkeypatch.setattr(settings, "provider", "anthropic")
    monkeypatch.setattr(settings, "model", "claude-opus-5-5")
    monkeypatch.setattr(settings, "worker_model", "claude-opus-5-5")
    monkeypatch.setattr(settings, "epoch_max_tokens", 150_000)
    monkeypatch.setattr(settings, "epoch_keep_turns", 4)
    monkeypatch.setattr(settings, "bash_approval", "dangerous")
    monkeypatch.setattr(settings, "web_render", False)
    monkeypatch.setattr(settings, "web_blocked_domains", [])
    monkeypatch.setattr(settings, "timezone", "UTC")
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


class ScriptedModel(GenericFakeChatModel):
    """Answers with the queued replies, records every request, and accepts any tool binding."""

    requests: list[list[BaseMessage]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        return self

    async def ainvoke(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
        self.requests.append(list(messages))
        return await super().ainvoke(messages, *args, **kwargs)


class Script:
    """The replies the fake model gives, in order, and the requests it received."""

    def __init__(self) -> None:
        self._replies: deque[AIMessage] = deque()
        self.requests: list[list[BaseMessage]] = []

    def reply(self, text: str = "", **kwargs: Any) -> "Script":
        self._replies.append(AIMessage(content=text, **kwargs))
        return self

    def call(self, tool: str, /, **args: Any) -> "Script":
        call_id = f"call-{len(self._replies)}"
        return self.reply(tool_calls=[{"name": tool, "args": args, "id": call_id}])

    def _next(self):
        while True:
            yield self._replies.popleft() if self._replies else AIMessage(content="ok")

    def model(self) -> ScriptedModel:
        model = ScriptedModel(messages=self._next(), disable_streaming=True)
        model.requests = self.requests
        return model


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Script:
    script = Script()
    monkeypatch.setattr(graph_module, "build_llm", lambda model: script.model())
    return script


class Digests:
    """A fake digester: records its inputs and returns `result(data)`."""

    def __init__(self) -> None:
        self.inputs: list[DigestInput] = []
        self.result: Callable[[DigestInput], EpochDigest] = lambda data: EpochDigest(
            episode_summary=f"episode {len(self.inputs)}",
            conversation_summary=f"summary {len(self.inputs)}",
            profile=data.profile,
            new_facts=[],
            outdated_fact_ids=[],
        )

    async def __call__(self, data: DigestInput) -> EpochDigest:
        self.inputs.append(data)
        return self.result(data)


@pytest.fixture
def digests(monkeypatch: pytest.MonkeyPatch) -> Digests:
    digests = Digests()
    monkeypatch.setattr(service_module, "build_digester", lambda model: digests)
    return digests


@pytest.fixture
async def service(script: Script, digests: Digests) -> AsyncIterator[AssistantService]:
    async with AssistantService.open() as svc:
        yield svc


async def collect(events: AsyncIterator[Any]) -> list[Any]:
    return [e async for e in events]
