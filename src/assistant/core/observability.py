"""Langfuse tracing with masking. Tracing is off unless Langfuse keys are set."""

import os
import re
from typing import Any

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "[API_KEY]"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), "[TG_TOKEN]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}"), "Bearer [TOKEN]"),
    (
        re.compile(r"(?i)\b([A-Z0-9_]*(?:key|secret|token|password)[A-Z0-9_]*)\s*[=:]\s*\S+"),
        r"\1=[SECRET]",
    ),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
]


def mask(*, data: Any, **kwargs: Any) -> Any:
    if isinstance(data, str):
        for pattern, label in PATTERNS:
            data = pattern.sub(label, data)
        return data
    if isinstance(data, dict):
        return {k: mask(data=v) for k, v in data.items()}
    if isinstance(data, list):
        return [mask(data=v) for v in data]
    return data


_enabled = False


def init_tracing() -> None:
    """Create the process-wide Langfuse client. Call once at process start."""
    global _enabled
    _enabled = bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))
    if _enabled:
        Langfuse(mask=mask)


def callbacks() -> list[CallbackHandler]:
    return [CallbackHandler()] if _enabled else []


def flush() -> None:
    if _enabled:
        from langfuse import get_client

        get_client().flush()
