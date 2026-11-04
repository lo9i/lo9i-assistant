"""The session helper (`python -m lo9i.session`): a small process of lo9i's that runs in the user's login session
on macOS, started by launchd as a LaunchAgent while the user is logged in (daemon/session_agent.py). A daemon started at
boot runs outside it, with no screen and no ssh agent; the helper opens links and apps on the screen for the plugins
that ask (protocol.py), and links the session's ssh agent where they get it (core/login_session.py)."""

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from lo9i.session.protocol import OpenRefusedError, code_digest, open_arguments

logger = logging.getLogger(__name__)

_OPEN = "/usr/bin/open"
_MAX_REQUEST = 8192

# Runs `open` with these arguments; returns why it failed, or "".
Opener = Callable[[list[str]], Awaitable[str]]


async def run_open(arguments: list[str]) -> str:
    process = await asyncio.create_subprocess_exec(
        _OPEN, *arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    output, _ = await process.communicate()
    return (
        ""
        if process.returncode == 0
        else output.decode(errors="replace").strip() or f"open exited {process.returncode}"
    )


class SessionHelper:
    def __init__(self, socket: Path, agent_link: Path, ssh_auth_sock: str, opener: Opener = run_open) -> None:
        self._socket, self._link, self._agent, self._opener = socket, agent_link, ssh_auth_sock, opener
        self._version = code_digest()
        self._quit = asyncio.Event()

    async def serve(self, stop: asyncio.Event) -> None:
        """Answers on the socket until `stop` is set or it's asked to quit."""
        self._socket.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._socket.unlink(missing_ok=True)
        server = await asyncio.start_unix_server(self._answer, path=str(self._socket), limit=_MAX_REQUEST)
        self._socket.chmod(0o600)
        self._link_agent()
        logger.info("Session helper ready on %s", self._socket)
        try:
            async with server:
                await _first(stop, self._quit)
        finally:
            self._unlink_agent()
            self._socket.unlink(missing_ok=True)

    async def _answer(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            answer = await self._handle(await reader.readline())
            writer.write(json.dumps(answer).encode() + b"\n")
            await writer.drain()
        except (OSError, ValueError) as e:
            logger.info("A request went unanswered: %s", e)
        finally:
            writer.close()

    async def _handle(self, line: bytes) -> dict[str, Any]:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            return {"error": "The request isn't JSON."}
        match request.get("op") if isinstance(request, dict) else None:
            case "open":
                return await self._open(str(request.get("url") or ""), str(request.get("app") or ""))
            case "version":
                return {"version": self._version}
            case "quit":
                self._quit.set()
                return {"ok": True}
            case _:
                return {"error": "Unknown request: op is open, version or quit."}

    async def _open(self, url: str, app: str) -> dict[str, Any]:
        try:
            arguments = open_arguments(url, app)
        except OpenRefusedError as e:
            return {"error": str(e)}
        if failed := await self._opener(arguments):
            logger.warning("Couldn't open %s: %s", arguments, failed)
            return {"error": failed}
        return {"ok": True}

    def _link_agent(self) -> None:
        """Points the link at this session's ssh agent; with none, a link from an earlier session goes."""
        self._link.unlink(missing_ok=True)
        if self._agent:
            self._link.symlink_to(self._agent)

    def _unlink_agent(self) -> None:
        if self._link.is_symlink() and os.readlink(self._link) == self._agent:
            self._link.unlink()


async def _first(*events: asyncio.Event) -> None:
    waits = [asyncio.create_task(e.wait()) for e in events]
    try:
        await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for wait in waits:
            wait.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await wait
