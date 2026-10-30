"""A plugin's check of the values it was given: `check:` in its server.yaml. It runs when they're saved, before they
are (installing the plugin, or changing its env or headers on the MCP page), so a wrong key shows in the dialog it
was typed in instead of failing the plugin's first use (a coding task, after minutes of retries).

    check:
      command: "{bin}/my-check"    # run with the plugin's env, keys and logins, in its folder: exit 0 when the
      args: []                     # values work, otherwise say why on stdout, in words for the user

    check:
      tool: check_account          # or a tool of its MCP server, called with no arguments: an error result says
                                   # why. The agent never gets it, and the apps don't list it.

A check that doesn't end within CHECK_SECONDS fails. A daemon from before checks installs the plugin without
running it, as it did, so `check:` needs no new format. What a plugin writes is in docs/plugin-checks.md."""

import asyncio
import contextlib
import os
import signal
from dataclasses import replace
from typing import Any

from langgraph.store.base import BaseStore
from mcp.client.session import IncomingMessage
from mcp.client.stdio import get_default_environment
from mcp.types import CallToolResult, TextContent

from assistant.core.config import settings
from assistant.core.mcp import data_key, folders, keys, logins, ssh_agent
from assistant.core.mcp.connection import ClientFactory, describe, open_client
from assistant.core.mcp.environment import Environments
from assistant.core.mcp.logins import SharedLogins
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.secret_store import SecretBox

CHECK_SECONDS = 60
# What the apps show of a check's words at most: a reason, not a log.
_MAX_REASON = 600
_PARTS = "its check must have either a command or a tool"


class CheckFailedError(McpServerError):
    """The plugin's check says the values it was given don't work; the text says why, for the user."""


def parse(value: object) -> dict[str, Any]:
    """The `check:` section as the server's fields; none without one. Raises ValueError for one that can't be used."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(_PARTS)
    command, tool = (str(value.get(key) or "").strip() for key in ("command", "tool"))
    args = value.get("args", [])
    if bool(command) == bool(tool):
        raise ValueError(_PARTS)
    if not isinstance(args, list):
        raise ValueError("its check args must be a list")
    return {"check_command": command, "check_args": [str(a) for a in args], "check_tool": tool}


class PluginChecks:
    def __init__(
        self,
        store: BaseStore,
        secrets: SecretBox,
        shared: SharedLogins,
        environments: Environments,
        factory: ClientFactory = open_client,
    ) -> None:
        """`shared` gives lo9i's logins a plugin can use (logins.py); `environments` rebuilds a lost environment
        before the check runs from it; `factory` connects to the server for a check that's one of its tools."""
        self._store = store
        self._secrets = secrets
        self._shared = shared
        self._environments = environments
        self._factory = factory

    async def run(self, server: McpServer) -> None:
        """Passes when the server has no check or its check says its values work. Raises CheckFailedError when they
        don't, or McpServerError when the check can't run."""
        if not (server.check_command or server.check_tool):
            return
        ready = await self._ready(server)
        reason = await (self._command(ready) if server.check_command else self._tool(ready))
        if reason is not None:
            raise CheckFailedError(f"{server.name}: {reason}")

    async def _ready(self, server: McpServer) -> McpServer:
        """The server as its processes would get it once saved: the values given, its saved keys for those left
        empty (keys.put keeps them), its data key and lo9i's logins."""
        saved = await keys.get(self._store, self._secrets, server.name)
        own = replace(
            server,
            env={k: v or saved.env.get(k, "") for k, v in server.env.items()},
            headers={k: v or saved.headers.get(k, "") for k, v in server.headers.items()},
        )
        keyed = await data_key.with_key(self._store, self._secrets, own)
        return ssh_agent.with_agent(logins.with_login(keyed, self._shared()))

    async def _command(self, server: McpServer) -> str | None:
        """Why the check command says the values don't work; None when it exits 0."""
        await self._environments.ensure(server.name, server.check_command)
        code = folders.code(server.name)
        env = get_default_environment() | {"TZ": settings.timezone} | server.env
        try:
            process = await asyncio.create_subprocess_exec(
                server.check_command,
                *server.check_args,
                env=env,
                cwd=code if code.is_dir() else None,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Its own process group, so a check that runs out of time stops with what it started.
                start_new_session=True,
            )
        except OSError as e:
            raise McpServerError(f"Couldn't run {server.name}'s check: {e}") from e
        return await _outcome(process)

    async def _tool(self, server: McpServer) -> str | None:
        """Why the check tool says the values don't work; None when it answers without an error."""
        if server.command:
            await self._environments.ensure(server.name, server.command)
        try:
            async with (
                asyncio.timeout(CHECK_SECONDS),
                self._factory(server, _ignore, None, ()) as client,
            ):
                result = await client.call_tool(server.check_tool, {})
        except TimeoutError:
            return f"its check didn't answer within {CHECK_SECONDS}s."
        except Exception as e:
            return f"its check couldn't run: {describe(e)}"
        return (_reason(_text(result)) or "its check failed.") if result.is_error else None


async def _outcome(process: asyncio.subprocess.Process) -> str | None:
    try:
        async with asyncio.timeout(CHECK_SECONDS):
            out, err = await process.communicate()
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
        return f"its check didn't finish within {CHECK_SECONDS}s."
    if process.returncode == 0:
        return None
    # What it says on stdout is for the user; stderr may be a traceback, so only its last line.
    last_error = (err.decode(errors="replace").strip().splitlines() or [""])[-1]
    return _reason(out.decode(errors="replace")) or _reason(last_error) or f"its check failed ({process.returncode})."


def _text(result: CallToolResult) -> str:
    return "\n".join(block.text for block in result.content if isinstance(block, TextContent))


def _reason(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _MAX_REASON else text[: _MAX_REASON - 1].rstrip() + "…"


async def _ignore(message: IncomingMessage) -> None:
    pass
