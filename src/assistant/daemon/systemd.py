"""Start at boot on Linux: a systemd user service (lo9i-assistant) for the daemon, running as the
user. It starts at boot without anyone logging in only while lingering is on for the user, which
needs an administrator once (`sudo loginctl enable-linger <user>`); without it, the service runs
while the user is logged in.

Ollama isn't managed here: its Linux installer sets up its own system service.

`python -m assistant.daemon.systemd` installs and enables the service; install.sh uses it.
"""

import asyncio
import getpass
import os
import sys
from pathlib import Path

from assistant.protocol import StartupError, StartupStatus

SERVICE = "lo9i-assistant"
# Set in the unit, so a daemon knows systemd started it.
MANAGED_ENV = "LO9I_SYSTEMD"
_LINGER_DIR = Path("/var/lib/systemd/linger")

__all__ = ["Service", "disable", "enable", "status"]


class Service:
    """A daemon systemd started stops through systemd: one that exited on its own would be started again
    (Restart=always). systemd stops it with SIGTERM, which stops the daemon cleanly."""

    def stop_refusal(self) -> str | None:
        return None

    async def stop(self, stop: asyncio.Event) -> None:
        # Without waiting: systemd waits for the daemon to exit, which waits for this call.
        await _systemctl("stop", "--no-block", SERVICE)


def status() -> StartupStatus:
    return StartupStatus(
        enabled=_wants_link().exists(),
        managed=os.environ.get(MANAGED_ENV) == "1",
        includes_ollama=False,
        platform="linux",
        starts_without_login=(_LINGER_DIR / getpass.getuser()).exists(),
    )


async def enable() -> StartupStatus:
    """Install and enable the service, and start it. A daemon already running keeps the socket
    until it steps aside; the service retries until then. Raises StartupError."""
    unit_path().parent.mkdir(parents=True, exist_ok=True)
    unit_path().write_text(unit())
    await _systemctl("daemon-reload")
    await _systemctl("enable", "--now", SERVICE)
    await _try_linger()
    return status()


async def disable() -> StartupStatus:
    """Disable and remove the service. A daemon it started keeps running until stopped or the
    computer restarts. Raises StartupError."""
    if unit_path().exists():
        await _systemctl("disable", SERVICE)
        unit_path().unlink()
        await _systemctl("daemon-reload")
    return status()


def unit() -> str:
    """The service: this Python running the daemon from this directory, restarted if it stops."""
    return "\n".join(
        [
            "[Unit]",
            "Description=lo9i assistant daemon",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            f"WorkingDirectory={os.getcwd()}",
            f'ExecStart="{sys.executable}" -m assistant.daemon',
            f"Environment={MANAGED_ENV}=1",
            # Always: a daemon that finds another one running exits, and retries until it can take over.
            "Restart=always",
            "RestartSec=5",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )


def unit_path() -> Path:
    return Path("~/.config/systemd/user").expanduser() / f"{SERVICE}.service"


def _wants_link() -> Path:
    return unit_path().parent / "default.target.wants" / f"{SERVICE}.service"


async def _systemctl(*args: str) -> None:
    code, output = await _run("systemctl", "--user", *args)
    if code != 0:
        raise StartupError(f"systemctl {' '.join(args)} failed: {output}")


async def _try_linger() -> None:
    """Lingering lets the service start at boot without a login. systemd allows users to turn it on
    for themselves on many systems; where it needs an administrator, status says it's off."""
    if not status().starts_without_login:
        await _run("loginctl", "enable-linger", getpass.getuser())


async def _run(*command: str) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    except FileNotFoundError as e:
        raise StartupError(f"{command[0]} isn't installed, so start at boot isn't available here.") from e
    output, _ = await proc.communicate()
    return proc.returncode or 0, output.decode(errors="replace").strip()


if __name__ == "__main__":
    print(asyncio.run(enable()))
