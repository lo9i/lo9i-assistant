"""What the apps can pick from when reading the log."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import get_args

from assistant.core.logs.components import COMPONENTS
from assistant.core.logs.entries import LogLevel
from assistant.core.logs.files import LogFileInfo
from assistant.core.logs.sources import LogSource, infos


@dataclass
class LogOptions:
    files: list[LogFileInfo]
    # Lowest first; each shows entries at that level or above.
    levels: list[str]
    components: list[str]


async def log_options(sources: Iterable[LogSource]) -> LogOptions:
    return LogOptions(await infos(sources), list(get_args(LogLevel)), list(COMPONENTS))
