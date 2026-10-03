"""Records every model call in the token ledger (core/usage/log.py) through LangChain callbacks,
so no caller counts tokens itself. Each place that calls a model attaches a meter with the call's
purpose; which conversation and channel it belongs to comes from the run's metadata (`CONVERSATION`
and `CHANNEL`), so a call made outside a run (archiving, titling) is recorded without them."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from assistant.core.usage.log import ModelCall, UsageLog
from assistant.core.usage.tokens import active_skill, estimate, input_parts, job_of, output_parts

# Run metadata keys (core/agent/runs.py) the meter reads.
CONVERSATION = "lo9i_thread_id"
CHANNEL = "lo9i_channel"


@dataclass(frozen=True)
class _Started:
    messages: list[BaseMessage]
    metadata: dict[str, Any]


class TokenMeter(AsyncCallbackHandler):
    def __init__(self, log: UsageLog, purpose: str) -> None:
        self._log = log
        self._purpose = purpose
        self._started: dict[UUID, _Started] = {}

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._started[run_id] = _Started(messages[0] if messages else [], metadata or {})

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        started = self._started.pop(run_id, None)
        reply = _reply(response)
        if started is None or reply is None:
            return
        call = _call(self._purpose, started, reply)
        parts = [*input_parts(started.messages, call.input_tokens), *output_parts(reply, call.output_tokens)]
        await self._log.record_model_call(call, parts)

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._started.pop(run_id, None)


def _call(purpose: str, started: _Started, reply: AIMessage) -> ModelCall:
    meta = started.metadata
    thread_id = str(meta.get(CONVERSATION, ""))
    usage = reply.usage_metadata
    if usage:
        details_in = usage.get("input_token_details") or {}
        details_out = usage.get("output_token_details") or {}
        counts = (
            usage["input_tokens"],
            details_in.get("cache_read", 0) or 0,
            details_in.get("cache_creation", 0) or 0,
            usage["output_tokens"],
            details_out.get("reasoning", 0) or 0,
        )
    else:
        counts = (estimate(started.messages), 0, 0, estimate([reply]), 0)
    return ModelCall(
        purpose,
        str(meta.get("ls_provider", "")),
        str(meta.get("ls_model_name", "")) or str(reply.response_metadata.get("model_name", "")) or "unknown",
        thread_id,
        str(meta.get(CHANNEL, "")),
        job_of(thread_id),
        active_skill(started.messages),
        *counts,
        estimated=not usage,
    )


def _reply(response: LLMResult) -> AIMessage | None:
    generations: Sequence[Any] = response.generations[0] if response.generations else []
    first = generations[0] if generations else None
    if isinstance(first, ChatGeneration) and isinstance(first.message, AIMessage):
        return first.message
    return None
