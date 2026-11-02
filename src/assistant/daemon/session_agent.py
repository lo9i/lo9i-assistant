"""The session helper's LaunchAgent (assistant/session/), installed with start at boot on macOS (launchd.py): launchd
runs it in the user's login session while they're logged in, for the daemon it starts at boot outside the session
(core/login_session.py). It's the user's own, so installing it needs no password.

A LaunchAgent is loaded at login. Installed while the user is logged in, it's loaded into their session at once when
launchd lets the daemon do that, which it may not from outside the session: it starts at the next login then. The
daemon makes sure at start that it's installed as it would install it now, and has a helper running older code quit,
for launchd to start it again with the code installed now (`ensure`)."""

import asyncio
import logging
import os
import plistlib
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from assistant.core import login_session
from assistant.core.logs.files import logs_dir
from assistant.session.protocol import HelperUnavailableError, ask, code_digest

logger = logging.getLogger(__name__)

LABEL = "com.lo9i.session"
_FOLDER = Path("~/Library/LaunchAgents")

# Runs launchctl with these arguments; returns its exit code and output.
Launchctl = Callable[[list[str]], Awaitable[tuple[int, str]]]


async def run_launchctl(arguments: list[str]) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        "launchctl", *arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    output, _ = await process.communicate()
    return process.returncode or 0, output.decode(errors="replace").strip()


def agent_plist() -> bytes:
    log = str(logs_dir() / "session-helper.log")
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": [sys.executable, "-m", "assistant.session"],
            # Where the daemon runs, so the helper reads the same .env.
            "WorkingDirectory": os.getcwd(),
            "RunAtLoad": True,
            # Again after any exit: a helper asked to quit for an update comes back with the new code.
            "KeepAlive": True,
            "ThrottleInterval": 10,
            # Only a session with a screen; an ssh login has none to open apps on.
            "LimitLoadToSessionType": "Aqua",
            "StandardOutPath": log,
            "StandardErrorPath": log,
        }
    )


class SessionAgent:
    def __init__(self, folder: Path = _FOLDER, launchctl: Launchctl = run_launchctl, uid: int | None = None) -> None:
        self._plist = folder.expanduser() / f"{LABEL}.plist"
        self._launchctl = launchctl
        self._domain = f"gui/{os.getuid() if uid is None else uid}"

    async def install(self) -> None:
        """Puts the plist in place and loads it into the user's session, when they're logged in and launchd lets the
        daemon; otherwise it's loaded at the next login."""
        self._plist.parent.mkdir(parents=True, exist_ok=True)
        logs_dir().mkdir(parents=True, exist_ok=True)
        self._plist.write_bytes(agent_plist())
        await self._launchctl(["bootout", f"{self._domain}/{LABEL}"])
        code, output = await self._launchctl(["bootstrap", self._domain, str(self._plist)])
        if code != 0:
            logger.info("The session helper starts at the next login (launchctl: %s).", output or code)

    async def remove(self) -> None:
        await self._launchctl(["bootout", f"{self._domain}/{LABEL}"])
        self._plist.unlink(missing_ok=True)

    async def ensure(self) -> None:
        """Installs it when it's missing or differs from the one installed now; else has a helper running older code
        quit, for launchd to start it again with the new code."""
        try:
            if not self._plist.exists() or self._plist.read_bytes() != agent_plist():
                await self.install()
                return
            await self._current()
        except OSError as e:
            logger.warning("Couldn't install the session helper: %s", e)

    async def _current(self) -> None:
        socket = login_session.socket_path()
        try:
            if (await ask(socket, {"op": "version"})).get("version") != code_digest():
                await ask(socket, {"op": "quit"})
                logger.info("The session helper runs older code: launchd starts it again with this one.")
        except HelperUnavailableError:
            pass  # Nobody is logged in: it starts with the code installed now at the next login.
