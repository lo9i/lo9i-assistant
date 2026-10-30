"""The lowest level the daemon records, chosen in the app (Settings → Logs) and stored as one Store
record; INFO until the user changes it. It applies to the assistant's own loggers at once. Libraries
stay at INFO, or at the chosen level when it's higher: at DEBUG some log every step they take
(watchfiles each file change, the log files' own included)."""

import logging
from typing import cast, get_args

from langgraph.store.base import BaseStore

from assistant.core.i18n import said
from assistant.core.logs.entries import LogLevel

_NAMESPACE = ("settings",)
_KEY = "logging"
_OWN = "assistant"
_LIBRARIES = logging.INFO

DEFAULT: LogLevel = "INFO"


class LogLevelError(ValueError):
    """A level that isn't one of the choices."""


async def load(store: BaseStore) -> LogLevel:
    item = await store.aget(_NAMESPACE, _KEY)
    level = item.value.get("level", DEFAULT) if item else DEFAULT
    return cast(LogLevel, level) if level in get_args(LogLevel) else DEFAULT


async def save(store: BaseStore, level: str) -> LogLevel:
    """Stores and applies it. Raises LogLevelError."""
    chosen = _checked(level)
    await store.aput(_NAMESPACE, _KEY, {"level": chosen})
    apply(chosen)
    return chosen


def apply(level: LogLevel) -> None:
    number = logging.getLevelNamesMapping()[level]
    logging.getLogger(_OWN).setLevel(number)
    logging.getLogger().setLevel(max(number, _LIBRARIES))


def _checked(level: str) -> LogLevel:
    if level not in get_args(LogLevel):
        raise LogLevelError(
            said("Unknown level: {level}. Choose one of: {levels}.", level=level, levels=", ".join(get_args(LogLevel)))
        )
    return cast(LogLevel, level)
