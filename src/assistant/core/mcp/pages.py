"""The web pages MCP servers come with: one process per enabled server that has one, listening on a
Unix socket in its data folder (core/mcp/folders.py). The daemon shows them to paired devices
(daemon/pages.py). A page that exits is started again (core/mcp/process.py).
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from langgraph.store.base import BaseStore
from mcp.client.stdio import get_default_environment

from assistant.core.config import settings
from assistant.core.mcp import data_key, folders, keys, servers, ssh_agent
from assistant.core.mcp.environment import Environments
from assistant.core.mcp.process import ProcessSpec, keep_running
from assistant.core.mcp.servers import McpServer
from assistant.core.secret_store import SecretBox

# A page's output and exits go under a child named after its server.
logger = logging.getLogger(__name__)


@dataclass
class _Running:
    server: McpServer
    stop: asyncio.Event
    task: asyncio.Task


class McpPages:
    name = "mcp-pages"

    def __init__(self, store: BaseStore, environments: Environments, secrets: SecretBox) -> None:
        self._store = store
        # A page gets its server's env, keys included (keys.py).
        self._secrets = secrets
        self._environments = environments
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
        found = [s for s in await servers.load_all(self._store) if s.enabled and s.page_command]
        filled = await keys.fill_all(self._store, self._secrets, found)
        wanted = {s.name: await data_key.with_key(self._store, self._secrets, s) for s in filled}
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
        socket = folders.page_socket(server.name)
        running = keep_running(
            f"page of {server.name}",
            lambda: _spec(server),
            stop,
            logger.getChild(server.name),
            lambda: socket.unlink(True),
            lambda: self._environments.ensure(server.name, server.page_command),
        )
        self._running[server.name] = _Running(server, stop, asyncio.create_task(running))

    async def _stop(self, name: str) -> None:
        running = self._running.pop(name)
        running.stop.set()
        await running.task


def _spec(server: McpServer) -> ProcessSpec:
    folders.page_socket(server.name).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    code = folders.code(server.name)
    env = get_default_environment() | {"TZ": settings.timezone} | ssh_agent.with_agent(server).env
    return ProcessSpec(server.page_command, server.page_args, env, code if code.is_dir() else None)


def _same_page(old: McpServer, new: McpServer) -> bool:
    return (old.page_command, old.page_args, old.env) == (new.page_command, new.page_args, new.env)
