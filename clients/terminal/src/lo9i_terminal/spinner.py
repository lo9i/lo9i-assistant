"""A one-line "working" indicator for the terminal while the agent has nothing to show yet."""

import asyncio
import sys
import time

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_INTERVAL = 0.1


class Spinner:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start(self, label: str) -> None:
        if self._task is None and sys.stdout.isatty():
            self._task = asyncio.create_task(self._spin(label))

    def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        self._task = None
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    async def _spin(self, label: str) -> None:
        started = time.monotonic()
        for i in range(sys.maxsize):
            elapsed = int(time.monotonic() - started)
            sys.stdout.write(f"\r{_FRAMES[i % len(_FRAMES)]} {label}… {elapsed}s")
            sys.stdout.flush()
            await asyncio.sleep(_INTERVAL)
