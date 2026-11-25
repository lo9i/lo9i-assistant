"""The container runtime the sandbox runs commands in: Docker or Podman, the first installed. Found by its command
alone, which is quick enough for every bash call; whether it answers (Docker Desktop started, Podman's machine up)
takes asking it, done only where a status is shown or the sandbox is turned on."""

import asyncio
import os
import pwd
import shutil
import sys
from dataclasses import dataclass

from lo9i.core.i18n import said
from lo9i.core.said import Said

# Where their installers put the commands, besides the usual folders: a daemon started by a service manager has a
# PATH of its own, so it doesn't rely on that.
_SEARCHED = (
    "/opt/homebrew/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    ":/Applications/Docker.app/Contents/Resources/bin:/opt/podman/bin"
)
_NAMES = ("docker", "podman")
# What the runtimes read to reach their daemon or machine, passed on when the daemon has them.
_PASSED = ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "CONTAINER_HOST", "CONTAINERS_CONF", "XDG_RUNTIME_DIR")
_ASK_SECONDS = 15


@dataclass(frozen=True)
class Runtime:
    name: str
    path: str

    @property
    def title(self) -> str:
        return "Docker" if self.name == "docker" else "Podman"


def find() -> Runtime | None:
    for name in _NAMES:
        path = shutil.which(name, path=_SEARCHED)
        if path:
            return Runtime(name, path)
    return None


def environment() -> dict[str, str]:
    """What the runtime's command needs: a PATH with its helpers (Docker Desktop's credential helpers), the user's
    home for its config and context (Docker Desktop's socket), and how to reach it when the daemon was told."""
    home = pwd.getpwuid(os.getuid()).pw_dir
    passed = {k: v for k, v in os.environ.items() if k in _PASSED}
    return {"PATH": _SEARCHED, "HOME": home, "LANG": "C.UTF-8", **passed}


async def answering(runtime: Runtime) -> bool:
    """Whether it can run containers now."""
    return await ask(runtime, "info") is not None


async def ask(runtime: Runtime, *args: str, seconds: float = _ASK_SECONDS) -> str | None:
    """Its output for `args`, or None when it failed or took longer than `seconds`."""
    proc = await asyncio.create_subprocess_exec(
        runtime.path,
        *args,
        env=environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=seconds)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return None
    return out.decode(errors="replace") if proc.returncode == 0 else None


def missing() -> Said:
    return said("Neither Docker nor Podman is installed on this computer, so commands can't run in a sandbox.")


def install_fix() -> Said:
    if sys.platform == "darwin":
        return said("Install Docker Desktop or Podman Desktop, start it, then turn the sandbox on.")
    return said("Install Docker or Podman, start it, then turn the sandbox on.")


def not_running(runtime: Runtime) -> Said:
    return said("{runtime} is installed but isn't running.", runtime=runtime.title)


def start_fix(runtime: Runtime) -> Said:
    if runtime.name == "podman":
        return said("Start Podman (Podman Desktop, or its machine), then try again.")
    if sys.platform == "darwin":
        return said("Open Docker Desktop and wait until it says it's running, then try again.")
    return said("Start Docker's service, then try again.")
