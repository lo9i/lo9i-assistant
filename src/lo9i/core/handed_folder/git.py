"""Asking git about the handed folder, when it's in a repository: which paths it ignores, and its status. Git runs in
the folder, with the user's own config, so their global ignore file counts as it does for them. It takes no
optional locks: the agent may be running git in the same repository meanwhile."""

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_TIMEOUT = 10


async def ignored(root: Path, paths: list[str]) -> set[str]:
    """Those of `paths` (relative to `root`) git ignores; none outside a repository, or when git can't say. A tracked
    file is never ignored."""
    if not paths:
        return set()
    out = await run(root, "check-ignore", "-z", "--stdin", given="\0".join(paths) + "\0", found=(0, 1))
    return set(_split(out)) if out else set()


async def prefix(root: Path) -> str | None:
    """Where `root` is in its repository ("" at its top, "src/" below it); None outside one."""
    out = await run(root, "rev-parse", "--show-prefix")
    return out.decode().strip() if out is not None else None


async def status(root: Path) -> bytes | None:
    """`git status` of what's under `root`, as porcelain v1 with NUL between entries; None outside a repository."""
    return await run(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal", "--", ".")


async def run(root: Path, *args: str, given: str | None = None, found: tuple[int, ...] = (0,)) -> bytes | None:
    """Git's output, or None when it isn't installed, the folder isn't in a repository, or it fails otherwise:
    a panel without git still shows the folder. `found` are the exit codes that aren't failures."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=root,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"},
            stdin=asyncio.subprocess.PIPE if given is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        return None
    return await _output(proc, given, found)


async def _output(proc: asyncio.subprocess.Process, given: str | None, found: tuple[int, ...]) -> bytes | None:
    try:
        sent = given.encode(errors="surrogateescape") if given is not None else None
        out, err = await asyncio.wait_for(proc.communicate(sent), _TIMEOUT)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning("git took more than %ss in the handed folder", _TIMEOUT)
        return None
    if proc.returncode not in found:
        logger.debug("git failed in the handed folder: %s", err.decode(errors="replace").strip())
        return None
    return out


def _split(out: bytes) -> list[str]:
    return [part.decode(errors="surrogateescape") for part in out.split(b"\0") if part]
