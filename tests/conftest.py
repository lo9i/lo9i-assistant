"""Shared fixtures. Every test runs on temporary data paths with a scripted fake model, so the
suite never touches ~/.lo9i, never calls a real model, and runs offline (except `-m live`)."""

import asyncio
import hashlib
import math
import re
from collections import deque
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import Field

import assistant.core.agent.model as model_module
import assistant.core.agent.service as service_module
import assistant.core.graph as graph_module
from assistant.core.agent import AssistantService
from assistant.core.config import settings
from assistant.core.conversation.digest import DigestInput, MemoryDigest
from assistant.core.memory.embedder import EmbeddingError


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name, value in {
        "database_path": tmp_path / "lo9i.db",
        "uploads_dir": tmp_path / "uploads",
        "workspace_dir": tmp_path / "workspace",
        "skills_dir": tmp_path / "skills",
        "mcp_dir": tmp_path / "mcp",
        "mcp_data_dir": tmp_path / "data",
        "persona_path": tmp_path / "SOUL.md",
        "daemon_socket": tmp_path / "daemon.sock",
        "secrets_key_path": tmp_path / "keys" / "secrets.key",
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


class FakeEmbedder:
    """Vectors from the texts' words, so texts sharing words are close. Stands in for the local
    embedding model, which would download on first use."""

    model = "fake-embedder"
    _DIMS = 64

    def __init__(self) -> None:
        self.failing = False

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        if self.failing:
            raise EmbeddingError("the model couldn't be downloaded")
        vector = [0.0] * self._DIMS
        for word in re.findall(r"\w+", text.lower()):
            vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % self._DIMS] += 1
        norm = math.sqrt(sum(v * v for v in vector)) or 1
        return [v / norm for v in vector]


@pytest.fixture(autouse=True)
def embedder(monkeypatch: pytest.MonkeyPatch) -> FakeEmbedder:
    fake = FakeEmbedder()
    monkeypatch.setattr(service_module, "E5Embedder", lambda: fake)
    return fake


class ScriptedModel(GenericFakeChatModel):
    """Answers with the queued replies, records every request and the tools bound for it."""

    requests: list[list[BaseMessage]] = Field(default_factory=list)
    bound: list[list[Any]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        self.bound.append(list(tools))
        return self

    async def ainvoke(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
        self.requests.append(list(messages))
        return await super().ainvoke(messages, *args, **kwargs)


class Script:
    """The replies the fake model gives, in order, and the requests it received."""

    def __init__(self) -> None:
        self._replies: deque[AIMessage] = deque()
        self.requests: list[list[BaseMessage]] = []
        # The tools bound for each request.
        self.bound: list[list[Any]] = []

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
        model.bound = self.bound
        return model


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Script:
    script = Script()
    monkeypatch.setattr(graph_module, "build_llm", lambda choice, model: script.model())
    return script


class Digests:
    """A fake digester: records its inputs and returns `result(data)`. It runs only when the test
    runs the memory writer (`service.memory_writer.write_all()`)."""

    def __init__(self) -> None:
        self.inputs: list[DigestInput] = []
        self.result: Callable[[DigestInput], MemoryDigest] = lambda data: MemoryDigest(
            episode_summary=f"episode {len(self.inputs)}",
            profile=data.profile,
            new_facts=[],
            outdated_fact_ids=[],
        )

    async def __call__(self, data: DigestInput) -> MemoryDigest:
        self.inputs.append(data)
        return self.result(data)


@pytest.fixture
def digests(monkeypatch: pytest.MonkeyPatch) -> Digests:
    digests = Digests()
    monkeypatch.setattr(model_module, "build_digester", lambda choice, usage: digests)
    return digests


class Summaries:
    """A fake summarizer: records the transcripts it was given and returns "summary <n>"."""

    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def __call__(self, previous_summary: str, transcript: str) -> str:
        self.inputs.append(transcript)
        return f"summary {len(self.inputs)}"


@pytest.fixture
def summaries(monkeypatch: pytest.MonkeyPatch) -> Summaries:
    summaries = Summaries()
    monkeypatch.setattr(model_module, "build_summarizer", lambda choice, usage: summaries)
    return summaries


class Titles:
    """A fake titler: records what it was given and returns `title`, or raises `error`."""

    def __init__(self) -> None:
        self.inputs: list[str] = []
        self.title = "Trip to Rome"
        self.error: Exception | None = None

    async def __call__(self, conversation: str) -> str:
        self.inputs.append(conversation)
        if self.error is not None:
            raise self.error
        return self.title


@pytest.fixture
def titles(monkeypatch: pytest.MonkeyPatch) -> Titles:
    titles = Titles()
    monkeypatch.setattr(model_module, "build_titler", lambda choice, usage: titles)
    return titles


@pytest.fixture
async def service(
    script: Script, digests: Digests, summaries: Summaries, titles: Titles
) -> AsyncIterator[AssistantService]:
    async with AssistantService.open() as svc:
        yield svc


async def collect(events: AsyncIterator[Any]) -> list[Any]:
    return [e async for e in events]


async def written(path: Path) -> str:
    """The file's text, once a background command has written it."""
    for _ in range(200):
        if path.exists() and path.read_text().strip():
            return path.read_text().strip()
        await asyncio.sleep(0.05)
    raise TimeoutError(f"{path} was never written")
