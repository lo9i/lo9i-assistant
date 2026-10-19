"""What started the daemon, which decides what stopping it from the app takes (daemon/shutdown.py). Each
service manager marks the daemons it starts with an environment variable: launchd (launchd.py) and systemd
(systemd.py); a daemon with neither was started by hand, by the terminal app or from a shell."""

import asyncio
import os

from assistant.daemon import launchd, systemd
from assistant.daemon.shutdown import ServiceManager


class ByHand:
    """Nothing starts it again, so it stops by exiting."""

    def stop_refusal(self) -> str | None:
        return None

    async def stop(self, stop: asyncio.Event) -> None:
        stop.set()


def current() -> ServiceManager:
    if os.environ.get(launchd.MANAGED_ENV) == "1":
        return launchd.Service()
    if os.environ.get(systemd.MANAGED_ENV) == "1":
        return systemd.Service()
    return ByHand()
