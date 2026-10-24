"""Start at boot: macOS LaunchDaemons for the daemon (and Ollama when it's used), running as the
user, from boot, without anyone logging in.

Installing needs administrator rights once; macOS shows its standard password dialog. launchd starts the
daemon again when it crashes, but not when it stops cleanly, so it can be stopped from the app.
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

from assistant.core.config import settings
from assistant.core.logs import output_path
from assistant.daemon import output
from assistant.protocol import StartupError, StartupStatus

DAEMON_LABEL = "com.lo9i.assistant"
OLLAMA_LABEL = "com.lo9i.ollama"
_PLIST_DIR = Path("/Library/LaunchDaemons")
# Set in the plist, so a daemon knows launchd started it.
MANAGED_ENV = "LO9I_LAUNCHD"
# Set in plists whose KeepAlive leaves the daemon stopped after it exits cleanly, so stopping it from the
# app lasts. Plists installed before restart it whatever its exit.
STAYS_STOPPED_ENV = "LO9I_STAYS_STOPPED"
# Started again after a crash, or after exiting because another daemon had the socket (EX_TEMPFAIL,
# daemon/server.py), but not after a clean stop.
_KEEP_ALIVE = {"SuccessfulExit": False}
# Where LaunchDaemons installed before the logs moved to their own folder send the daemon's output.
LEGACY_OUTPUT = Path("~/.lo9i/daemon.log")


__all__ = ["Service", "StartupError", "disable", "enable", "move_legacy_output", "status"]


class Service:
    """A daemon launchd started stops by exiting cleanly. Stopping it through launchd would need an
    administrator: a LaunchDaemon belongs to the system."""

    def stop_refusal(self) -> str | None:
        if os.environ.get(STAYS_STOPPED_ENV) == "1":
            return None
        return (
            "macOS would start the assistant again at once: start at boot was turned on before it could be "
            "stopped from the app. Turn start at boot off and on again to allow it."
        )

    async def stop(self, stop: asyncio.Event) -> None:
        stop.set()


def status() -> StartupStatus:
    return StartupStatus(
        enabled=_plist_path(DAEMON_LABEL).exists(),
        managed=os.environ.get(MANAGED_ENV) == "1",
        includes_ollama=_plist_path(OLLAMA_LABEL).exists(),
        platform="macos",
    )


async def enable() -> StartupStatus:
    # launchd opens the daemon's output file but doesn't create its folder.
    output_path().parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        plists = {DAEMON_LABEL: daemon_plist()}
        if _uses_ollama() and (ollama := ollama_plist()):
            plists[OLLAMA_LABEL] = ollama
        staged = {label: _stage(Path(tmp), label, data) for label, data in plists.items()}
        await _run_as_admin(" && ".join(install_commands(label, path) for label, path in staged.items()))
    return status()


async def disable() -> StartupStatus:
    await _run_as_admin(" ; ".join(uninstall_commands(label) for label in (DAEMON_LABEL, OLLAMA_LABEL)))
    return status()


def daemon_plist() -> bytes:
    home = str(Path.home())
    return plistlib.dumps(
        {
            "Label": DAEMON_LABEL,
            "ProgramArguments": [sys.executable, "-m", "assistant.daemon"],
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


def uninstall_commands(label: str) -> str:
    return f"launchctl bootout system/{label} 2>/dev/null; rm -f {shlex.quote(str(_plist_path(label)))}"


async def _run_as_admin(script: str) -> None:
    applescript = f'do shell script "{_applescript_escape(script)}" with administrator privileges'
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", applescript, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        message = stderr.decode(errors="replace").strip()
        raise StartupError("Cancelled." if "User canceled" in message else f"macOS refused: {message}")


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
