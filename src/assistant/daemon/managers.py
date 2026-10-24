"""What started the daemon, which decides what stopping it from the app takes (daemon/shutdown.py). Each
service manager marks the daemons it starts with an environment variable: launchd (launchd.py) and systemd
(systemd.py); a daemon with neither was started by hand, by the terminal app or from a shell. One started by
hand while start at boot is on runs beside the service, which keeps trying to start (each try steps aside while
this one runs) and would take over once it exits: stopping it then has to stop those tries too (`Beside`)."""

import asyncio
import os
import shutil
import sys

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
    if sys.platform == "darwin":
        return launchd.Beside()
    if sys.platform.startswith("linux") and shutil.which("systemctl"):
        return systemd.Beside()
    return ByHand()
