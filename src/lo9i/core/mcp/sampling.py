"""A server's request for text from the model (MCP sampling): the model writes it, the worker model unless the server
prefers intelligence to speed and cost, at most MAX_TOKENS, and each server at most SAMPLES_PER_HOUR times an hour.
The call is recorded in the token ledger as `mcp_sampling`. What it writes goes to the server, never into the
conversation: the run's callbacks aren't given to it, so nothing it writes streams to the apps as the reply.

Before a server that isn't trusted gets one, the user approves it (answers.py), seeing what the model is asked."""

import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from mcp.types import (
    AudioContent,
    CreateMessageRequestParams,
    CreateMessageResult,
    ImageContent,
    ModelPreferences,
    SamplingMessage,
    TextContent,
)

from lo9i.core.hidden_text import strip_hidden
from lo9i.core.llm import build_llm, metered
from lo9i.core.llm.choice import ModelChoice
from lo9i.core.usage.log import UsageLog
from lo9i.core.usage.meter import TokenMeter

MAX_TOKENS = 2000
SAMPLES_PER_HOUR = 30
# What the approval shows of the request, at most.
_SHOWN = 2000
_HOUR = 3600.0


class Sampler:
    def __init__(self, choice: Callable[[], ModelChoice], usage: UsageLog) -> None:
        """`choice`: the model in use, read for each request."""
        self._choice = choice
        self._usage = usage
        self._sampled: dict[str, deque[float]] = defaultdict(deque)

    def over_limit(self, server: str) -> bool:
        """It had SAMPLES_PER_HOUR in the last hour."""
        sampled = self._sampled[server]
        while sampled and sampled[0] < time.monotonic() - _HOUR:
            sampled.popleft()
        return len(sampled) >= SAMPLES_PER_HOUR

    async def sample(self, server: str, params: CreateMessageRequestParams) -> CreateMessageResult:
        self._sampled[server].append(time.monotonic())
        choice = self._choice()
        model = choice.model if _wants_intelligence(params.model_preferences) else choice.worker_model
        llm = metered(
            build_llm(choice, model, min(params.max_tokens, MAX_TOKENS)), TokenMeter(self._usage, "mcp_sampling")
        )
        # Callbacks of its own: the run's would stream what it writes to the apps as the assistant's reply.
        reply = await llm.ainvoke(messages(params), config={"callbacks": []})
        return CreateMessageResult(
            role="assistant", content=TextContent(type="text", text=reply.text), model=model, stop_reason="endTurn"
        )


def messages(params: CreateMessageRequestParams) -> list[BaseMessage]:
    system = [SystemMessage(params.system_prompt)] if params.system_prompt else []
    return [*system, *(_message(m) for m in params.messages)]


def shown(server: str, params: CreateMessageRequestParams) -> dict[str, Any]:
    """The approval request (core/tools/approval.py): what the model is asked to write."""
    asked = "\n\n".join(_text(m) for m in params.messages)
    system = f"[system] {params.system_prompt}\n\n" if params.system_prompt else ""
    text = strip_hidden(system + asked)
    return {
        "tool": f"{server} (sampling)",
        "command": text if len(text) <= _SHOWN else text[:_SHOWN] + "…",
        "reason": f"{server} asks the model to write text for it (up to {min(params.max_tokens, MAX_TOKENS)} tokens)",
    }


def _wants_intelligence(preferences: ModelPreferences | None) -> bool:
    if preferences is None or preferences.intelligence_priority is None:
        return False
    others = max(preferences.speed_priority or 0, preferences.cost_priority or 0)
    return preferences.intelligence_priority > others


def _message(message: SamplingMessage) -> BaseMessage:
    blocks = [_block(c) for c in _contents(message)]
    content: Any = [b for b in blocks if b is not None]
    return AIMessage(content=content) if message.role == "assistant" else HumanMessage(content=content)


def _contents(message: SamplingMessage) -> list[Any]:
    return list(message.content) if isinstance(message.content, list) else [message.content]


def _block(content: Any) -> dict[str, Any] | None:
    if isinstance(content, TextContent):
        return {"type": "text", "text": content.text}
    if isinstance(content, ImageContent):
        return {"type": "image", "base64": content.data, "mime_type": content.mime_type}
    if isinstance(content, AudioContent):
        return {"type": "text", "text": "[audio left out]"}
    return None


def _text(message: SamplingMessage) -> str:
    parts = [c.text if isinstance(c, TextContent) else f"[{c.type}]" for c in _contents(message)]
    return f"[{message.role}] " + " ".join(parts)
