"""The web pages MCP servers come with: one process per enabled server that has one, listening on a
Unix socket in its data folder (core/mcp/folders.py). The daemon shows them to paired devices
(daemon/pages.py). A page that exits is started again, waiting longer each time.
"""

import asyncio
import contextlib
import logging
import os
import signal
from dataclasses import dataclass
from pathlib import Path

from langgraph.store.base import BaseStore
from mcp.client.stdio import get_default_environment

from assistant.core.mcp import folders, servers
from assistant.core.mcp.servers import McpServer

logger = logging.getLogger(__name__)

_FIRST_RETRY_SECONDS = 5
_MAX_RETRY_SECONDS = 300
# A page that ran this long before exiting starts again at the first wait.
_HEALTHY_SECONDS = 60
_STOP_SECONDS = 5


@dataclass
class _Running:
    server: McpServer
    stop: asyncio.Event
    task: asyncio.Task


class McpPages:
    name = "mcp-pages"

    def __init__(self, store: BaseStore) -> None:
        self._store = store
        self._running: dict[str, _Running] = {}
        self._active = False

    async def run(self, stop: asyncio.Event) -> None:
        """Run the pages of the enabled servers until `stop` is set."""
        self._active = True
        try:
            await self.reload()
            await stop.wait()
        finally:
            self._active = False
            for name in list(self._running):
                await self._stop(name)

    async def reload(self) -> None:
        """Bring the pages in line with the saved servers. Called after every change."""
        if not self._active:
            return
        wanted = {s.name: s for s in await servers.load_all(self._store) if s.enabled and s.page_command}
        for name, running in list(self._running.items()):
            if name not in wanted or not _same_page(running.server, wanted[name]):
                await self._stop(name)
        for name, server in wanted.items():
            if name not in self._running:
                self._start(server)

    async def restart(self, name: str) -> None:
        """Start the page again even if its command didn't change: its code did (an update)."""
        if self._active and name in self._running:
            await self._stop(name)
        await self.reload()

    def socket(self, name: str) -> Path | None:
        """Where a running page listens, or None if the server has no page running."""
        return folders.page_socket(name) if name in self._running else None

    def _start(self, server: McpServer) -> None:
        stop = asyncio.Event()
        self._running[server.name] = _Running(server, stop, asyncio.create_task(_keep_running(server, stop)))

    async def _stop(self, name: str) -> None:
        running = self._running.pop(name)
        running.stop.set()
        await running.task


async def _keep_running(server: McpServer, stop: asyncio.Event) -> None:
    wait = _FIRST_RETRY_SECONDS
    while not stop.is_set():
        started = asyncio.get_running_loop().time()
        code = await _run_once(server, stop)
        if stop.is_set():
            return
        if asyncio.get_running_loop().time() - started > _HEALTHY_SECONDS:
            wait = _FIRST_RETRY_SECONDS
        logger.warning("The page of %s exited (%s); starting it again in %ss", server.name, code, wait)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), wait)
        wait = min(wait * 2, _MAX_RETRY_SECONDS)


async def _run_once(server: McpServer, stop: asyncio.Event) -> int | None:
    """Run the page until it exits or `stop` is set. Its output goes to the daemon's log."""
    socket = folders.page_socket(server.name)
    socket.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            server.page_command,
            *server.page_args,
            env=get_default_environment() | server.env,
            cwd=folders.code(server.name) if folders.code(server.name).is_dir() else None,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            # Its own process group, so stopping it also stops what it started (uv starts the app).
            start_new_session=True,
        )
    except OSError as e:
        logger.warning("Couldn't start the page of %s: %s", server.name, e)
        return None
    log = asyncio.create_task(_log_output(server.name, proc))
    ended = asyncio.create_task(stop.wait())
    await asyncio.wait({ended, asyncio.ensure_future(proc.wait())}, return_when=asyncio.FIRST_COMPLETED)
    ended.cancel()
    if proc.returncode is None:
        await _terminate(proc)
    await log
    socket.unlink(missing_ok=True)
    return proc.returncode


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), _STOP_SECONDS)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        await proc.wait()


async def _log_output(name: str, proc: asyncio.subprocess.Process) -> None:
    assert proc.stdout is not None
    async for line in proc.stdout:
        logger.info("[page %s] %s", name, line.decode(errors="replace").rstrip())


def _same_page(old: McpServer, new: McpServer) -> bool:
    return (old.page_command, old.page_args, old.env) == (new.page_command, new.page_args, new.env)
