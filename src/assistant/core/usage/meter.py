"""Records every model call in the token ledger (core/usage/log.py) through LangChain callbacks,
so no caller counts tokens itself. Each place that calls a model attaches a meter with the call's
purpose; which conversation and channel it belongs to comes from the run's metadata (`CONVERSATION`
and `CHANNEL`), so a call made outside a run (archiving, titling) is recorded without them. Beside it on the model
goes its `check` (llm.metered), which holds each call to the spending limits before it's made (budget.py), and after
it's recorded the meter has the limits nearly reached told. A model checked as it's set up (agent/model.py) gets only
the meter, so saving a model is never held."""

import logging
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
        self.check = SpendingCheck(log)

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
        if self._log.guard is not None:
            await self._log.guard.after_call(call.thread_id)

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._started.pop(run_id, None)


class SpendingCheck(AsyncCallbackHandler):
    """Before each model call: one over a spending limit raises OverBudgetError (budget.py), and the call isn't made.
    A handler of its own, since its errors reach the caller, and the meter's mustn't."""

    raise_error = True

    def __init__(self, log: UsageLog) -> None:
        self._log = log

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if self._log.guard is not None:
            await self._log.guard.check(str((metadata or {}).get(CONVERSATION, "")))


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


class _Refusals(logging.Filter):
    """LangChain logs each error a callback raises as a warning before passing it on. A call a spending limit refused
    isn't a fault (runs.py logs the run's end at INFO), so that record goes; any other error of the check stays."""

    def filter(self, record: logging.LogRecord) -> bool:
        said = record.getMessage()
        return not (said.startswith(f"Error in {SpendingCheck.__name__}.") and ": OverBudgetError(" in said)


logging.getLogger("langchain_core.callbacks.manager").addFilter(_Refusals())
