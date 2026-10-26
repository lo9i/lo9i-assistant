"""A run that failed, recorded in its conversation: the checkpoint keeps only the last run's error, so without a
mark an earlier failed run reads as a message without a reply, like a run stopped before it answered. The mark
is an assistant message with no text, its error in `response_metadata`; no model call sends it (`without_marks`),
history shows it as the error the run ended with (display.py), and the doctor counts it (core/doctor/)."""

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

RUN_FAILED = "lo9i_run_failed"


def mark(error: str, step: str) -> AIMessage:
    """`step`: the graph node the run failed at, "" when it isn't known."""
    return AIMessage("", response_metadata={RUN_FAILED: {"error": error, "step": step}})


def of(message: BaseMessage) -> dict[str, Any] | None:
    """The mark's error and step, or None for any other message."""
    found = message.response_metadata.get(RUN_FAILED) if isinstance(message, AIMessage) else None
    return found if isinstance(found, dict) else None


def without_marks(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    return [m for m in messages if of(m) is None]
