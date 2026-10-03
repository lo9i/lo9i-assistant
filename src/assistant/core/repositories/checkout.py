"""A fresh download of a repository's default branch, deleted afterwards."""

import asyncio
import contextlib
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from assistant.core.repositories.errors import RepositoryError

_TIMEOUT = 120


@contextlib.asynccontextmanager
async def checkout(url: str) -> AsyncIterator[tuple[Path, str]]:
    """The repository's root folder and its commit."""
    check_url(url)
    temp = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="lo9i-repo-"))
    try:
        root = temp / "repo"
        commit = await _fetch(url, root)
        yield root, commit
    finally:
        await asyncio.to_thread(shutil.rmtree, temp, True)


def check_url(url: str) -> None:
    # Only https: other git transports can run local commands or read local files.
    if not url.startswith("https://") or any(c.isspace() for c in url):
        raise RepositoryError("Give the repository's https:// address, for example https://github.com/user/extras.")


def default_name(url: str) -> str:
    """What a repository that is one skill or one server is called: its last path part."""
    return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git").lower()


async def _fetch(url: str, root: Path) -> str:
    await _git("clone", "--depth", "1", "--quiet", "--", url, str(root))
    return (await _git("-C", str(root), "rev-parse", "HEAD")).strip()


async def _git(*args: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            # No prompts: a private repository fails instead of waiting for a password nobody types.
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_TERMINAL_PROMPT": "0", "LANG": "C.UTF-8"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise RepositoryError("Installing from a repository needs git on the computer running the assistant.") from e
    return await _output(proc)


async def _output(proc: asyncio.subprocess.Process) -> str:
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
    except TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise RepositoryError(f"The repository didn't download within {_TIMEOUT} seconds.") from e
    if proc.returncode != 0:
        lines = stderr.decode(errors="replace").strip().splitlines()
        raise RepositoryError(f"Couldn't get the repository: {lines[-1] if lines else 'git failed'}")
    return stdout.decode(errors="replace")
