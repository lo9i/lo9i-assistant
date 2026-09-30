"""Connecting to the daemon on its Unix socket, starting it in the background if it isn't running."""

import asyncio
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx

from assistant.client.daemon_client import DaemonClient
from assistant.client.errors import DaemonUnavailableError
from assistant.core.config import settings
from assistant.protocol import CLIENT_HEADER, CLIENT_ID_HEADER

_BASE = "http://lo9i"
# Replies can take minutes; only connecting should be quick.
_TIMEOUT = httpx.Timeout(connect=5, read=None, write=60, pool=5)
_LOG = "~/.lo9i/daemon.log"
_START_TIMEOUT_SECONDS = 60
_READY_CHECK_SECONDS = 0.25


@asynccontextmanager
async def connect() -> AsyncIterator[DaemonClient]:
    transport = httpx.AsyncHTTPTransport(uds=str(Path(settings.daemon_socket).expanduser()))
    headers = {CLIENT_HEADER: "cli", CLIENT_ID_HEADER: uuid4().hex}
    async with httpx.AsyncClient(transport=transport, base_url=_BASE, timeout=_TIMEOUT, headers=headers) as http:
        if not await _is_ready(http):
            _start_daemon()
            await _wait_until_ready(http)
        yield DaemonClient(http)


async def _is_ready(http: httpx.AsyncClient) -> bool:
    try:
        return (await http.get("/health")).status_code == 200
    except httpx.TransportError:
        return False


def _start_daemon() -> None:
    log = Path(_LOG).expanduser()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as out:
        subprocess.Popen(
            [sys.executable, "-m", "assistant.daemon"],
            stdout=out,
            stderr=out,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )


async def _wait_until_ready(http: httpx.AsyncClient) -> None:
    for _ in range(int(_START_TIMEOUT_SECONDS / _READY_CHECK_SECONDS)):
        if await _is_ready(http):
            return
        await asyncio.sleep(_READY_CHECK_SECONDS)
    raise DaemonUnavailableError(f"The daemon didn't start. See {_LOG}.")
