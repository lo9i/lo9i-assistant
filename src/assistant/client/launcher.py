"""Starts the daemon in the background when a client can't reach it."""

import asyncio
import subprocess
import sys
from pathlib import Path

from assistant.core.config import settings

_LOG = "~/.lo9i/daemon.log"
_START_TIMEOUT_SECONDS = 60


def start_daemon() -> None:
    log = Path(_LOG).expanduser()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as out:
        subprocess.Popen(
            [sys.executable, "-m", "assistant.daemon"],
            stdout=out, stderr=out, stdin=subprocess.DEVNULL, start_new_session=True,
        )


async def wait_until_ready(is_ready) -> None:
    for _ in range(_START_TIMEOUT_SECONDS * 4):
        if await is_ready():
            return
        await asyncio.sleep(0.25)
    raise RuntimeError(f"The daemon didn't start. See {_LOG}.")


def socket_path() -> str:
    return str(Path(settings.daemon_socket).expanduser())
