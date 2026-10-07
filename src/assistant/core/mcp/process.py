"""Keeps a plugin's process running: a page (core/mcp/pages.py) or a chat channel
(core/channels/processes.py). A process that exits is started again, waiting longer each time; its
output goes to the daemon's log."""

import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_FIRST_RETRY_SECONDS = 5
_MAX_RETRY_SECONDS = 300
# A process that ran this long before exiting starts again at the first wait.
_HEALTHY_SECONDS = 60
_STOP_SECONDS = 5


@dataclass(frozen=True)
class ProcessSpec:
    command: str
    args: list[str]
    env: dict[str, str]
    cwd: Path | None


async def keep_running(
    label: str,
    spec: Callable[[], ProcessSpec],
    stop: asyncio.Event,
    after: Callable[[], None] | None = None,
    prepare: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Run the process until `stop` is set. `prepare` runs and `spec` is asked again before every start
    (core/mcp/environment.py rebuilds a lost environment); `after` runs after every exit."""
    wait = _FIRST_RETRY_SECONDS
    while not stop.is_set():
        started = asyncio.get_running_loop().time()
        code = await _start(label, spec, prepare, stop)
        if after is not None:
            after()
        if stop.is_set():
            return
        if asyncio.get_running_loop().time() - started > _HEALTHY_SECONDS:
            wait = _FIRST_RETRY_SECONDS
        logger.warning("The %s exited (%s); starting it again in %ss", label, code, wait)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), wait)
        wait = min(wait * 2, _MAX_RETRY_SECONDS)


async def _start(
    label: str, spec: Callable[[], ProcessSpec], prepare: Callable[[], Awaitable[None]] | None, stop: asyncio.Event
) -> int | None:
    """The exit code of one run, None when it couldn't start."""
    try:
        if prepare is not None:
            await prepare()
    except Exception as e:
        logger.warning("Couldn't get the %s ready: %s", label, e)
        return None
    return await _run_once(label, spec(), stop)


async def _run_once(label: str, spec: ProcessSpec, stop: asyncio.Event) -> int | None:
    """Run the process until it exits or `stop` is set."""
    try:
        proc = await asyncio.create_subprocess_exec(
            spec.command,
            *spec.args,
            env=spec.env,
            cwd=spec.cwd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            # Its own process group, so stopping it also stops what it started (uv starts the app).
            start_new_session=True,
        )
    except OSError as e:
        logger.warning("Couldn't start the %s: %s", label, e)
        return None
    log = asyncio.create_task(_log_output(label, proc))
    ended = asyncio.create_task(stop.wait())
    await asyncio.wait({ended, asyncio.ensure_future(proc.wait())}, return_when=asyncio.FIRST_COMPLETED)
    ended.cancel()
    if proc.returncode is None:
        await _terminate(proc)
    await log
    return proc.returncode


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), _STOP_SECONDS)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        await proc.wait()


async def _log_output(label: str, proc: asyncio.subprocess.Process) -> None:
    assert proc.stdout is not None
    async for line in proc.stdout:
        logger.info("[%s] %s", label, line.decode(errors="replace").rstrip())
