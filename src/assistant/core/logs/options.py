"""What the apps can pick from when reading the log."""

import asyncio
from dataclasses import dataclass
from typing import get_args

from assistant.core.logs.components import COMPONENTS
from assistant.core.logs.entries import LogLevel
from assistant.core.logs.files import LOG_FILES, LogFileInfo, info


@dataclass
class LogOptions:
    files: list[LogFileInfo]
    # Lowest first; each shows entries at that level or above.
    levels: list[str]
    components: list[str]


async def log_options() -> LogOptions:
    files = await asyncio.to_thread(lambda: [info(f) for f in LOG_FILES.values()])
    return LogOptions(files, list(get_args(LogLevel)), list(COMPONENTS))
