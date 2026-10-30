"""A fresh download of a repository's default branch, deleted afterwards, and its latest commit."""

import asyncio
import base64
import contextlib
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from assistant.core.i18n import said
from assistant.core.repositories.errors import RepositoryError

_TIMEOUT = 120
# What git says when a repository wants a sign-in it didn't get (or refused the one it got).
_SIGN_IN_NEEDED = ("could not read Username", "terminal prompts disabled", "Authentication failed")


@contextlib.asynccontextmanager
async def checkout(url: str, token: str = "") -> AsyncIterator[tuple[Path, str]]:
    """The repository's root folder and its commit. `token` reads a private repository."""
    check_url(url)
    temp = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="lo9i-repo-"))
    try:
        root = temp / "repo"
        commit = await _fetch(url, root, token)
        yield root, commit
    finally:
        await asyncio.to_thread(shutil.rmtree, temp, True)


async def latest_commit(url: str, token: str = "") -> str:
    """The commit of the repository's default branch, asked without downloading it."""
    check_url(url)
    output = (await _git("ls-remote", "--", url, "HEAD", auth=_auth(url, token))).split()
    if not output:
        raise RepositoryError(said("The repository has no commits."))
    return output[0]


def check_url(url: str) -> None:
    # Only https: other git transports can run local commands or read local files.
    if not url.startswith("https://") or any(c.isspace() for c in url):
        raise RepositoryError(
            said("Give the repository's https:// address, for example https://github.com/user/extras.")
        )


def default_name(url: str) -> str:
    """What a repository that is one skill or one server is called: its last path part."""
    return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git").lower()


async def _fetch(url: str, root: Path, token: str) -> str:
    await _git("clone", "--depth", "1", "--quiet", "--", url, str(root), auth=_auth(url, token))
    return (await _git("-C", str(root), "rev-parse", "HEAD")).strip()


def _auth(url: str, token: str) -> dict[str, str]:
    """A token as git config in the environment, so it's on no command line and in no file: an
    Authorization header sent only to the repository's host. The user name is ignored by GitHub and
    most hosts, which take a token as the password."""
    if not token:
        return {}
    scheme, _, rest = url.partition("://")
    credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"http.{scheme}://{rest.split('/', 1)[0]}/.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {credentials}",
    }


async def _git(*args: str, auth: dict[str, str] | None = None) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            # No prompts: a private repository fails instead of waiting for a password nobody types.
            # No system config either: Apple's git turns on the Keychain there, which would read a
            # private repository with the user's own sign-in on a Mac but not on Linux. A private
            # repository is read with the token it was added with, the same on every host.
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "LANG": "C.UTF-8",
                **(auth or {}),
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise RepositoryError(
            said("Installing from a repository needs git on the computer running the assistant.")
        ) from e
    return await _output(proc)


async def _output(proc: asyncio.subprocess.Process) -> str:
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
    except TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise RepositoryError(said("The repository didn't download within {seconds} seconds.", seconds=_TIMEOUT)) from e
    if proc.returncode != 0:
        lines = stderr.decode(errors="replace").strip().splitlines()
        if any(sign in line for line in lines for sign in _SIGN_IN_NEEDED):
            raise RepositoryError(
                said(
                    "Couldn't get the repository: it's private, or the token can't read it. Add it with a token that "
                    "can read its contents."
                )
            )
        raise RepositoryError(
            said("Couldn't get the repository: {error}", error=lines[-1] if lines else said("git failed"))
        )
    return stdout.decode(errors="replace")
