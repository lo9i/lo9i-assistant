"""Starting and stopping a plugin's worker for a task. A worker is started through a shell that exits at
once, so it belongs to no one: the daemon never waits for it, and it keeps running when the daemon
restarts. These block: async code calls them in a thread."""

import contextlib
import os
import signal
import subprocess
from pathlib import Path

# Runs the worker in the background with its output in a log, and exits.
_DETACH = '"$@" </dev/null >>"$WORKER_LOG" 2>&1 &'


def start(command: list[str], folder: Path, env: dict[str, str], cwd: Path | None) -> None:
    """Runs `command` with the task's folder as its last argument."""
    environment = {**env, "WORKER_LOG": str(folder / "worker.log")}
    subprocess.run(["/bin/sh", "-c", _DETACH, "sh", *command, str(folder)], env=environment, cwd=cwd, check=True)


def wake(pid: int) -> None:
    """Tells the worker a message is waiting in its inbox. Only the worker: the commands it started would
    end on a signal they don't expect."""
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGUSR1)


def stop(pid: int) -> None:
    """Stops the worker and everything it started: it leads its own process group (docs/agent-plugins.md)."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGTERM)
