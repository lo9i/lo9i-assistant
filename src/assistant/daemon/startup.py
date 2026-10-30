"""Start at boot, for the API: LaunchDaemons on macOS (launchd.py), a systemd user service on Linux
(systemd.py). After enabling, a daemon that wasn't started that way steps aside, so the one the
system starts takes over. What's installed can be out of date (an older LaunchDaemon, `StartupStatus.outdated`):
installing it again replaces it, and a daemon it started exits once no run is in progress, for the system to start
it from the new one (`Shutdown.relaunch`)."""

import asyncio
import os
import shutil
import sys
from collections.abc import Callable
from typing import Protocol

from assistant.core.i18n import said
from assistant.daemon import launchd, systemd
from assistant.protocol import StartupError, StartupStatus

# Long enough for the API to answer the request that enabled start at boot.
_STEP_ASIDE_SECONDS = 2


class Backend(Protocol):
    """What launchd.py and systemd.py offer."""

    def status(self) -> StartupStatus: ...

    async def enable(self) -> StartupStatus: ...

    async def disable(self) -> StartupStatus: ...

    async def install_for_relaunch(self, pid: int) -> None:
        """Installs it again while the daemon `pid` it started runs; the system loads it once that one exits."""
        ...


# Has the daemon exit once no run is in progress, for its service manager to start it again; says what needs it.
Relaunch = Callable[[str], object]


class Startup:
    def __init__(self, stop: asyncio.Event, relaunch: Relaunch = lambda needed_by: None) -> None:
        self._stop = stop
        self._relaunch = relaunch
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

    async def reinstall(self) -> StartupStatus:
        """Installs start at boot again, as turning it on now would. Raises StartupError when it's off."""
        backend = self._require()
        if not backend.status().enabled:
            raise StartupError(said("Start at boot is off. Turn it on instead."))
        if not backend.status().managed:
            return await self.enable()
        await backend.install_for_relaunch(os.getpid())
        self._relaunch(said("Start at boot was installed again"))
        return backend.status()

    def _require(self) -> Backend:
        if self._backend is None:
            raise StartupError(said("Start at boot works on macOS and on Linux with systemd."))
        return self._backend


def _backend() -> Backend | None:
    if sys.platform == "darwin":
        return launchd
    if sys.platform.startswith("linux") and shutil.which("systemctl"):
        return systemd
    return None
