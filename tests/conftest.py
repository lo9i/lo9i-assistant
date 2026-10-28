"""Shared fixtures. Every test runs on temporary data paths with a scripted fake model, so the
suite never touches ~/.lo9i, never calls a real model, and runs offline (except `-m live`)."""

import asyncio
import hashlib
import math
import re
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import Field

import assistant.core.agent.model as model_module
import assistant.core.agent.service as service_module
import assistant.core.graph as graph_module
import assistant.core.home.builder as home_builder_module
import assistant.core.subagent as subagent_module
from assistant.core.agent import AssistantService
from assistant.core.config import settings
from assistant.core.conversation.digest import DigestInput, MemoryDigest
from assistant.core.conversation.dispatch import QUICK, Candidate, Pick
from assistant.core.conversation.titles import Titled
from assistant.core.home.model import SectionContent
from assistant.core.llm import windows
from assistant.core.memory.embedder import EmbeddingError


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name, value in {
        "database_path": tmp_path / "lo9i.db",
        "uploads_dir": tmp_path / "uploads",
        "logs_dir": tmp_path / "logs",
        "workspace_dir": tmp_path / "workspace",
        "agent_workspace_dir": tmp_path / "claude-workspace",
        "skills_dir": tmp_path / "skills",
        "mcp_dir": tmp_path / "mcp",
        "mcp_data_dir": tmp_path / "data",
        "persona_path": tmp_path / "SOUL.md",
        "prompts_dir": tmp_path / "prompts",
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


@pytest.fixture(autouse=True)
def model_windows(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """No provider is asked for a model's context window (tests are offline): none is known, unless a test puts a
    lookup here, by provider."""
    lookups: dict[str, Any] = {}
    monkeypatch.setattr(windows, "_LOOKUPS", lookups)
    return lookups


class Dispatcher:
    """A fake dispatch classifier: returns the queued picks in order, `default` when none is left, and
    records each message with the candidates it chose among and the inbox's exchange in progress."""

    def __init__(self, default: Pick) -> None:
        self.default = default
        self.picks: deque[Pick] = deque()
        self.inputs: list[tuple[str, list[Candidate]]] = []
        self.exchanges: list[str] = []

    async def __call__(self, message: str, candidates: Any, exchange: str) -> Pick:
        self.inputs.append((message, list(candidates)))
        self.exchanges.append(exchange)
        return self.picks.popleft() if self.picks else self.default


@pytest.fixture(autouse=True)
def inbox_answers(monkeypatch: pytest.MonkeyPatch) -> Dispatcher:
    """Every message in the inbox is a quick question the inbox answers, so tests of the agent can talk
    there (`service.session`); the `dispatch` fixture routes them instead."""
    dispatcher = Dispatcher(Pick(QUICK, 1.0, ""))
    monkeypatch.setattr(graph_module, "build_classifier", lambda choice, usage: dispatcher)
    return dispatcher


@pytest.fixture
def dispatch(inbox_answers: Dispatcher) -> Dispatcher:
    """The inbox routes messages with a fake classifier: to a new conversation, sure, unless picks are
    queued."""
    inbox_answers.default = Pick("", 1.0, "")
    return inbox_answers


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
    """Answers with the queued replies, records every request and the tools bound for it. A queued error is raised
    by the call whose turn it is instead."""

    requests: list[list[BaseMessage]] = Field(default_factory=list)
    bound: list[list[Any]] = Field(default_factory=list)
    replies: deque[AIMessage | Exception] = Field(default_factory=deque)

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        self.bound.append(list(tools))
        return self

    async def ainvoke(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
        self.requests.append(list(messages))
        if self.replies and isinstance(error := self.replies[0], Exception):
            self.replies.popleft()
            raise error
        return await super().ainvoke(messages, *args, **kwargs)


class Script:
    """The replies the fake model gives, in order, and the requests it received."""

    def __init__(self) -> None:
        self._replies: deque[AIMessage | Exception] = deque()
        self.requests: list[list[BaseMessage]] = []
        # The tools bound for each request.
        self.bound: list[list[Any]] = []

    def reply(self, text: str = "", **kwargs: Any) -> "Script":
        self._replies.append(AIMessage(content=text, **kwargs))
        return self

    def call(self, tool: str, /, **args: Any) -> "Script":
        call_id = f"call-{len(self._replies)}"
        return self.reply(tool_calls=[{"name": tool, "args": args, "id": call_id}])

    def refuse(self, error: Exception) -> "Script":
        """The model call whose turn it is raises `error`."""
        self._replies.append(error)
        return self

    def _next(self) -> Iterator[AIMessage]:
        while True:
            # A queued error is taken by the call before it gets here (ScriptedModel.ainvoke).
            yield cast(AIMessage, self._replies.popleft()) if self._replies else AIMessage(content="ok")

    def model(self) -> ScriptedModel:
        model = ScriptedModel(messages=self._next(), disable_streaming=True)
        model.requests = self.requests
        model.bound = self.bound
        model.replies = self._replies
        return model


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Script:
    script = Script()
    monkeypatch.setattr(graph_module, "build_llm", lambda choice, model: script.model())
    # Subagents answer from the same script, in the order the calls happen.
    monkeypatch.setattr(subagent_module, "build_llm", lambda choice, model: script.model())
    # So do Home's sections; their format step finds nothing unless a test uses `formats`.
    monkeypatch.setattr(home_builder_module, "build_llm", lambda choice, model: script.model())
    monkeypatch.setattr(home_builder_module, "build_structured", lambda choice, model, schema, meter=None: Formats())
    return script


class Formats:
    """Home's format step (core/home/builder.py): the queued answers in order (an exception is raised), then an
    empty section. A section whose title is in `failing` fails."""

    def __init__(self) -> None:
        self.answers: deque[Any] = deque()
        self.requests: list[list[BaseMessage]] = []
        self.failing: set[str] = set()
        # When set, each answer waits for it: a model that takes its time.
        self.gate: asyncio.Event | None = None

    async def ainvoke(self, messages: list[BaseMessage]) -> Any:
        self.requests.append(messages)
        if self.gate is not None:
            await self.gate.wait()
        if any(f"Section: {title}\n" in messages[-1].text for title in self.failing):
            raise RuntimeError("the model is down")
        answer = self.answers.popleft() if self.answers else SectionContent(items=[])
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def formats(monkeypatch: pytest.MonkeyPatch, script: Script) -> Formats:
    formats = Formats()
    monkeypatch.setattr(home_builder_module, "build_structured", lambda choice, model, schema, meter=None: formats)
    return formats


class Digests:
    """A fake digester: records its inputs and returns `result(data)`. It runs only when the test
    runs the memory writer (`service.memory_writer.write_all()`)."""

    def __init__(self) -> None:
        self.inputs: list[DigestInput] = []
        # When set, each digest waits for it: a model call that doesn't answer.
        self.answer: asyncio.Event | None = None
        self.result: Callable[[DigestInput], MemoryDigest] = lambda data: MemoryDigest(
            episode_summary=f"episode {len(self.inputs)}",
            profile=data.profile,
            new_facts=[],
            outdated_fact_ids=[],
        )

    async def __call__(self, data: DigestInput) -> MemoryDigest:
        self.inputs.append(data)
        if self.answer is not None:
            await self.answer.wait()
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
    """A fake titler: records what it was given and returns `title` and `tags`, or raises `error`."""

    def __init__(self) -> None:
        self.inputs: list[str] = []
        self.title = "Trip to Rome"
        self.tags = ["rome"]
        self.error: Exception | None = None

    async def __call__(self, conversation: str) -> Titled:
        self.inputs.append(conversation)
        if self.error is not None:
            raise self.error
        return Titled(self.title, self.tags)


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
