"""Start at boot: macOS LaunchDaemons for the daemon (and Ollama when it's used), running as the
user, from boot, without anyone logging in. Outside the user's login session it has no screen and no ssh agent, so
the session helper's LaunchAgent goes with it (session_agent.py).

Installing needs administrator rights once; macOS shows its standard password dialog. launchd starts the
daemon again when it crashes, but not when it stops cleanly, so it can be stopped from the app.

A daemon started by hand while start at boot is on runs beside the LaunchDaemon, which launchd keeps trying to start:
stopping it stops those tries first, until the next boot, which asks for the password too (`Beside`).

A LaunchDaemon installed by an older version differs from the one turning it on installs now (where the daemon's
output goes, whether it can be stopped from the app): its status says how (`outdated`), and installing it again
replaces it. The daemon it runs is replaced once it exits (`install_for_relaunch`), so its runs end first.
"""

import asyncio
import getpass
import os
import plistlib
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

from lo9i.core import login_session
from lo9i.core.config import settings
from lo9i.core.i18n import said
from lo9i.core.logs import output_path
from lo9i.daemon import output
from lo9i.daemon.session_agent import SessionAgent
from lo9i.protocol import StartupError, StartupStatus, StopRefusedError

DAEMON_LABEL = "com.lo9i.assistant"
OLLAMA_LABEL = "com.lo9i.ollama"
_PLIST_DIR = Path("/Library/LaunchDaemons")
# Set in the plist, so a daemon knows launchd started it, outside the login session.
MANAGED_ENV = login_session.FROM_BOOT_ENV
# Set in plists whose KeepAlive leaves the daemon stopped after it exits cleanly, so stopping it from the
# app lasts. Plists installed before restart it whatever its exit.
STAYS_STOPPED_ENV = "LO9I_STAYS_STOPPED"
# Started again after a crash, or after exiting because another daemon had the socket (EX_TEMPFAIL,
# daemon/server.py), but not after a clean stop.
_KEEP_ALIVE = {"SuccessfulExit": False}
# Where LaunchDaemons installed before the logs moved to their own folder send the daemon's output.
LEGACY_OUTPUT = Path("~/.lo9i/daemon.log")


__all__ = [
    "AdminCancelledError",
    "Beside",
    "Service",
    "StartupError",
    "disable",
    "enable",
    "install_for_relaunch",
    "keep_session_helper",
    "move_legacy_output",
    "outdated",
    "status",
    "stop_tries",
]


class Service:
    """A daemon launchd started stops by exiting cleanly. Stopping it through launchd would need an
    administrator: a LaunchDaemon belongs to the system."""

    def stop_refusal(self) -> str | None:
        if os.environ.get(STAYS_STOPPED_ENV) == "1":
            return None
        return said(
            "macOS would start the assistant again at once: start at boot was turned on before it could be "
            "stopped from the app. Turn start at boot off and on again to allow it."
        )

    def stop_note(self) -> str | None:
        return None

    async def before_stop(self) -> str | None:
        return None

    async def stop(self, stop: asyncio.Event) -> None:
        stop.set()


class Beside:
    """A daemon started by hand. While start at boot is on, launchd keeps trying to start the LaunchDaemon (each try
    steps aside while this one runs), and the next one would take over once it exits. Stopping those tries needs an
    administrator, so a stop asks for the password as it's asked for and stops them until the next boot: the plist
    stays, so start at boot still starts the assistant then. Without the password the stop is refused."""

    def stop_refusal(self) -> str | None:
        return None

    def stop_note(self) -> str | None:
        if not status().enabled:
            return None
        return said(
            "Start at boot is on: stopping asks for the administrator password on this Mac, so macOS stops trying to "
            "start the assistant until the next boot."
        )

    async def before_stop(self) -> str | None:
        """Raises StopRefusedError when the password wasn't given."""
        if not status().enabled:
            return None
        try:
            await stop_tries()
        except AdminCancelledError as e:
            raise StopRefusedError(
                said(
                    "The administrator password wasn't given. Start at boot is on, so macOS would start the "
                    "assistant again at once: stopping needs the password, or start at boot turned off. Restarting "
                    "needs neither."
                )
            ) from e
        except StartupError as e:
            raise StopRefusedError(
                said("macOS didn't stop trying to start the assistant: {reason}", reason=str(e))
            ) from e
        return said("macOS stopped trying to start the assistant until the next boot")

    async def stop(self, stop: asyncio.Event) -> None:
        stop.set()


class AdminCancelledError(StartupError):
    """The user cancelled macOS's administrator password dialog."""


def status() -> StartupStatus:
    return StartupStatus(
        enabled=_plist_path(DAEMON_LABEL).exists(),
        managed=os.environ.get(MANAGED_ENV) == "1",
        includes_ollama=_plist_path(OLLAMA_LABEL).exists(),
        platform="macos",
        outdated=outdated(),
    )


def outdated() -> list[str]:
    """How the installed LaunchDaemon differs from the one turning start at boot on installs now; empty when it
    doesn't, or none is installed or it can't be read."""
    try:
        installed = plistlib.loads(_plist_path(DAEMON_LABEL).read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return []
    wanted = plistlib.loads(daemon_plist())
    return [why(installed) for key, why in _DIFFERENCES if installed.get(key) != wanted.get(key)]


# What an older LaunchDaemon may differ in, and what that does.
_DIFFERENCES = [
    (
        "KeepAlive",
        lambda _: said("macOS starts the assistant again whatever its exit, so it can't be stopped from the app."),
    ),
    (
        "StandardOutPath",
        lambda installed: said(
            "It sends the daemon's output to {path}, which Settings → Logs doesn't show.",
            path=installed.get("StandardOutPath", "nowhere"),
        ),
    ),
    (
        "ProgramArguments",
        lambda installed: said(
            "It starts the assistant with {command}, not the way it starts now.",
            command=" ".join(installed.get("ProgramArguments", [])),
        ),
    ),
]


async def install_for_relaunch(pid: int) -> None:
    """Installs the LaunchDaemon again while the daemon `pid` it runs keeps running: macOS loads the new one once
    that daemon has exited. The commands run apart from the daemon, which launchd stops with everything it
    started."""
    output_path().parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        staged = _stage(Path(tmp), DAEMON_LABEL, daemon_plist())
        await _run_as_admin(relaunch_commands(DAEMON_LABEL, staged, pid))
    await SessionAgent().install()


async def enable() -> StartupStatus:
    # launchd opens the daemon's output file but doesn't create its folder.
    output_path().parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        plists = {DAEMON_LABEL: daemon_plist()}
        if _uses_ollama() and (ollama := ollama_plist()):
            plists[OLLAMA_LABEL] = ollama
        staged = {label: _stage(Path(tmp), label, data) for label, data in plists.items()}
        await _run_as_admin(" && ".join(install_commands(label, path) for label, path in staged.items()))
    await SessionAgent().install()
    return status()


async def stop_tries() -> None:
    """Stops launchd trying to start the LaunchDaemon until the next boot, which loads its plist again: a daemon
    started by hand runs beside it. Asks for the administrator's password. Raises StartupError."""
    await _run_as_admin(f"launchctl bootout system/{DAEMON_LABEL} 2>/dev/null; true")


async def disable() -> StartupStatus:
    await _run_as_admin(" ; ".join(uninstall_commands(label) for label in (DAEMON_LABEL, OLLAMA_LABEL)))
    await SessionAgent().remove()
    return status()


async def keep_session_helper() -> None:
    """At the daemon's start: while start at boot is on, the session helper's LaunchAgent installed and its code
    current (SessionAgent.ensure), for one installed before it came or before an update."""
    if status().enabled:
        await SessionAgent().ensure()


def daemon_plist() -> bytes:
    home = str(Path.home())
    return plistlib.dumps(
        {
            "Label": DAEMON_LABEL,
            "ProgramArguments": [sys.executable, "-m", "lo9i.daemon"],
            "WorkingDirectory": os.getcwd(),
            "UserName": getpass.getuser(),
            "RunAtLoad": True,
            "KeepAlive": _KEEP_ALIVE,
            "ThrottleInterval": 10,
            "StandardOutPath": str(output_path()),
            "StandardErrorPath": str(output_path()),
            "EnvironmentVariables": {
                "HOME": home,
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                MANAGED_ENV: "1",
                STAYS_STOPPED_ENV: "1",
            },
        }
    )


def move_legacy_output() -> bool:
    """A LaunchDaemon installed before the logs moved sends the daemon's output to LEGACY_OUTPUT until
    start at boot is turned off and on, which needs the administrator's password, so the daemon sends
    its output to output_path() itself, where the Logs page reads it. Only what's printed before this
    runs at start stays behind. Returns whether it moved."""
    if not output.is_stderr(LEGACY_OUTPUT.expanduser()):
        return False
    output.send_output_to(output_path())
    return True


def ollama_plist() -> bytes | None:
    binary = shutil.which("ollama")
    if binary is None:
        return None
    log = str(Path("~/.lo9i/ollama.log").expanduser())
    return plistlib.dumps(
        {
            "Label": OLLAMA_LABEL,
            "ProgramArguments": [binary, "serve"],
            "UserName": getpass.getuser(),
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 10,
            "StandardOutPath": log,
            "StandardErrorPath": log,
            "EnvironmentVariables": {
                "HOME": str(Path.home()),
                "OLLAMA_CONTEXT_LENGTH": os.environ.get("OLLAMA_CONTEXT_LENGTH", "32768"),
            },
        }
    )


def install_commands(label: str, staged: Path) -> str:
    target = shlex.quote(str(_plist_path(label)))
    return " && ".join(
        [
            f"launchctl bootout system/{label} 2>/dev/null; true",
            f"cp {shlex.quote(str(staged))} {target}",
            f"chown root:wheel {target}",
            f"chmod 644 {target}",
            f"launchctl bootstrap system {target}",
        ]
    )


def relaunch_commands(label: str, staged: Path, pid: int) -> str:
    """The plist in place now; the job loaded again in the background once `pid` has exited."""
    target = shlex.quote(str(_plist_path(label)))
    reload = (
        f"while kill -0 {pid} 2>/dev/null; do sleep 1; done; "
        f"launchctl bootout system/{label} 2>/dev/null; launchctl bootstrap system {target}"
    )
    return " && ".join(
        [
            f"cp {shlex.quote(str(staged))} {target}",
            f"chown root:wheel {target}",
            f"chmod 644 {target}",
            f"({reload}) >/dev/null 2>&1 &",
        ]
    )


def uninstall_commands(label: str) -> str:
    return f"launchctl bootout system/{label} 2>/dev/null; rm -f {shlex.quote(str(_plist_path(label)))}"


async def _run_as_admin(script: str) -> None:
    applescript = f'do shell script "{_applescript_escape(script)}" with administrator privileges'
    # A session of its own: launchd stops a LaunchDaemon's daemon with everything it started, and what this runs
    # may need to outlast it (`install_for_relaunch`).
    proc = await asyncio.create_subprocess_exec(
        "osascript",
        "-e",
        applescript,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        message = stderr.decode(errors="replace").strip()
        if "User canceled" in message:
            raise AdminCancelledError("Cancelled.")
        raise StartupError(f"macOS refused: {message}")


def _applescript_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _stage(folder: Path, label: str, data: bytes) -> Path:
    path = folder / f"{label}.plist"
    path.write_bytes(data)
    return path


def _plist_path(label: str) -> Path:
    return _PLIST_DIR / f"{label}.plist"


def _uses_ollama() -> bool:
    return settings.provider == "openai" and ":11434" in os.environ.get("OPENAI_BASE_URL", "")
