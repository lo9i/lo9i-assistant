"""Records every tool call of a run through LangChain callbacks, so no tool needs to know about it."""

import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langgraph.errors import GraphInterrupt

from assistant.core.tools.approval import UNATTENDED_DENIAL
from assistant.core.usage.log import ToolCall, UsageLog

_REJECTED = "The user rejected this"


class UsageTracker(AsyncCallbackHandler):
    def __init__(self, log: UsageLog, thread_id: str, channel: str) -> None:
        self._log = log
        self._thread_id = thread_id
        self._channel = channel
        self._started: dict[UUID, tuple[str, str | None, float]] = {}

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name") or kwargs.get("name", "")
        skill = (inputs or {}).get("name") if name == "use_skill" else None
        self._started[run_id] = (name, skill, time.monotonic())

    async def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        await self._finish(run_id, _status(_text(output)))

    async def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        if isinstance(error, GraphInterrupt):
            # Paused for approval; the call runs again, and is recorded, when the run resumes.
            self._started.pop(run_id, None)
            return
        await self._finish(run_id, "error")

    async def _finish(self, run_id: UUID, status: str) -> None:
        started = self._started.pop(run_id, None)
        if started is None:
            return
        name, skill, began = started
        duration = round((time.monotonic() - began) * 1000)
        await self._log.record(ToolCall(name, skill, self._thread_id, self._channel, duration, status))


def _text(output: Any) -> str:
    content = getattr(output, "content", output)
    return content if isinstance(content, str) else str(content)


def _status(output: str) -> str:
    return "denied" if output.startswith((UNATTENDED_DENIAL, _REJECTED)) else "ok"
