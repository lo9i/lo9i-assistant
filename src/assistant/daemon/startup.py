"""Start at boot, for the API: LaunchDaemons on macOS (launchd.py), a systemd user service on Linux
(systemd.py). After enabling, a daemon that wasn't started that way steps aside, so the one the
system starts takes over."""

import asyncio
import shutil
import sys
from typing import Protocol

from assistant.daemon import launchd, systemd
from assistant.protocol import StartupError, StartupStatus

# Long enough for the API to answer the request that enabled start at boot.
_STEP_ASIDE_SECONDS = 2


class Backend(Protocol):
    """What launchd.py and systemd.py offer."""

    def status(self) -> StartupStatus: ...

    async def enable(self) -> StartupStatus: ...

    async def disable(self) -> StartupStatus: ...


class Startup:
    def __init__(self, stop: asyncio.Event) -> None:
        self._stop = stop
        self._backend = _backend()

    def status(self) -> StartupStatus:
        if self._backend is None:
            return StartupStatus(enabled=False, managed=False, includes_ollama=False, platform="unsupported")
        return self._backend.status()

    async def enable(self) -> StartupStatus:
        result = await self._require().enable()
        if not result.managed:
            asyncio.get_running_loop().call_later(_STEP_ASIDE_SECONDS, self._stop.set)
        return result

    async def disable(self) -> StartupStatus:
        return await self._require().disable()

    def _require(self) -> Backend:
        if self._backend is None:
            raise StartupError("Start at boot works on macOS and on Linux with systemd.")
        return self._backend


def _backend() -> Backend | None:
    if sys.platform == "darwin":
        return launchd
    if sys.platform.startswith("linux") and shutil.which("systemctl"):
        return systemd
    return None
