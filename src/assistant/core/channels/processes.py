"""Runs the chat channels installed as plugins: one process per enabled plugin with a `channel:`
command (core/mcp/install.py), started again when it exits (core/mcp/process.py). Each start gets a
new token that reaches only its own channel's routes (core/channels/hub.py, daemon/auth.py)."""

import asyncio
from dataclasses import dataclass

from langgraph.store.base import BaseStore
from mcp.client.stdio import get_default_environment

from assistant.core.channels.hub import ChannelHub
from assistant.core.config import settings
from assistant.core.mcp import folders, keys, servers
from assistant.core.mcp.environment import Environments
from assistant.core.mcp.process import ProcessSpec, keep_running
from assistant.core.mcp.servers import McpServer
from assistant.core.secret_store import SecretBox


@dataclass
class _Running:
    server: McpServer
    stop: asyncio.Event
    task: asyncio.Task


class ChannelProcesses:
    name = "channel-processes"

    def __init__(self, store: BaseStore, hub: ChannelHub, environments: Environments, secrets: SecretBox) -> None:
        self._store = store
        # A channel's process gets its plugin's env, keys included (core/mcp/keys.py).
        self._secrets = secrets
        self._hub = hub
        self._environments = environments
        self._running: dict[str, _Running] = {}
        self._active = False

    async def run(self, stop: asyncio.Event) -> None:
        """Run the enabled channels until `stop` is set."""
        self._active = True
        try:
            await self.reload()
            await stop.wait()
        finally:
            self._active = False
            for name in list(self._running):
                await self._stop(name)

    async def reload(self) -> None:
        """Bring the processes in line with the saved plugins. Called after every change."""
        if not self._active:
            return
        found = [s for s in await servers.load_all(self._store) if s.enabled and s.channel_command]
        wanted = {s.name: s for s in await keys.fill_all(self._store, self._secrets, found)}
        for name, running in list(self._running.items()):
            if name not in wanted or not _same(running.server, wanted[name]):
                await self._stop(name)
        for name, server in wanted.items():
            if name not in self._running:
                self._start(server)

    async def restart(self, name: str) -> None:
        """Start the channel again even if its command didn't change: its code did (an update)."""
        if self._active and name in self._running:
            await self._stop(name)
        await self.reload()

    def _start(self, server: McpServer) -> None:
        stop = asyncio.Event()
        running = keep_running(
            f"channel {server.name}",
            lambda: self._spec(server),
            stop,
            prepare=lambda: self._environments.ensure(server.name, server.channel_command),
        )
        self._running[server.name] = _Running(server, stop, asyncio.create_task(running))

    async def _stop(self, name: str) -> None:
        running = self._running.pop(name)
        running.stop.set()
        await running.task
        self._hub.revoke(name)

    def _spec(self, server: McpServer) -> ProcessSpec:
        code = folders.code(server.name)
        env = get_default_environment() | {"TZ": settings.timezone} | server.env | self._daemon_env(server.name)
        return ProcessSpec(server.channel_command, server.channel_args, env, code if code.is_dir() else None)

    def _daemon_env(self, name: str) -> dict[str, str]:
        """How the process reaches the daemon (docs/channel-plugins.md)."""
        return {
            "LO9I_URL": f"http://127.0.0.1:{settings.daemon_port}",
            "LO9I_CHANNEL": name,
            "LO9I_CHANNEL_TOKEN": self._hub.issue_token(name),
        }


def _same(old: McpServer, new: McpServer) -> bool:
    return (old.channel_command, old.channel_args, old.env) == (new.channel_command, new.channel_args, new.env)
