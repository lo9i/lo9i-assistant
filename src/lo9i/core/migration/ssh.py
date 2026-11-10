"""Signing in to another computer over SSH, to move lo9i there (moving to it is daemon/moves.py's): with a password,
a key file on this computer, the user's ssh agent or their default keys, never sending a key anywhere. A host from a
plugin (core/mcp/ssh_hosts.py) comes with its own OpenSSH config, which is read for that one connection from a
private temporary folder, never written where ssh would read it later; a host typed in reads the user's
~/.ssh/config, never written either.

Host keys: a host the user's ~/.ssh/known_hosts or lo9i's own (`known_hosts`, beside the secrets key) knows must show
the key they keep; one neither knows is trusted the first time, as ssh's `StrictHostKeyChecking accept-new`, and its
key kept in lo9i's own file, so a key that changes later is refused."""

import asyncio
import contextlib
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncssh

from lo9i.core.config import settings
from lo9i.core.i18n import said
from lo9i.core.mcp.ssh_agent import agent_socket
from lo9i.core.migration.errors import MigrationError

_CONNECT_SECONDS = 20
# A move can sit for minutes in one command (installing lo9i); the host is asked now and then that it's still there.
_KEEPALIVE_SECONDS = 30


@dataclass(frozen=True)
class SshTarget:
    # An address or a name in the user's ssh config, or the Host entry of `config`.
    host: str
    user: str = ""
    # 0: the config's, else 22.
    port: int = 0
    password: str = ""
    # A private key file on this computer, only to sign in with.
    key_path: str = ""
    # A plugin's OpenSSH config for the host; "" for the user's own.
    config: str = ""


class KnownHosts:
    """The host keys the user's known_hosts and lo9i's own keep, and the one met the first time."""

    def __init__(self, own: Path, users: Path) -> None:
        self._own = own
        self._users = users
        self._known = asyncssh.SSHKnownHosts()
        # A host neither file knew, trusted this time: (its known_hosts name, its key).
        self.met: tuple[str, asyncssh.SSHKey] | None = None

    @classmethod
    def lo9i(cls) -> "KnownHosts":
        own = Path(settings.secrets_key_path).expanduser().parent / "known_hosts"
        return cls(own, Path("~/.ssh/known_hosts").expanduser())

    async def load(self) -> None:
        self._known = await asyncio.to_thread(self._read)

    def _read(self) -> asyncssh.SSHKnownHosts:
        files = [str(p) for p in (self._users, self._own) if p.is_file()]
        return asyncssh.read_known_hosts(files) if files else asyncssh.SSHKnownHosts()

    def trusts(self, host: str, addr: str, port: int | None, key: asyncssh.SSHKey) -> bool:
        keys, _, revoked, *_ = self._known.match(host, addr, port)
        if key in revoked:
            return False
        if keys:
            return key in keys
        self.met = (host if not port or port == 22 else f"[{host}]:{port}", key)
        return True

    async def remember(self) -> str:
        """Keeps the key of the host met the first time; returns its fingerprint, "" when there was none."""
        if self.met is None:
            return ""
        name, key = self.met
        line = f"{name} {key.export_public_key().decode().strip()}\n"
        await asyncio.to_thread(_append_private, self._own, line)
        return key.get_fingerprint()


class _Client(asyncssh.SSHClient):
    def __init__(self, known: KnownHosts) -> None:
        self._known = known

    def validate_host_public_key(self, host: str, addr: str, port: int, key: asyncssh.SSHKey) -> bool:
        return self._known.trusts(host, addr, port, key)


@contextlib.asynccontextmanager
async def connected(target: SshTarget, known: KnownHosts) -> AsyncIterator[asyncssh.SSHClientConnection]:
    """Raises MigrationError saying why it couldn't sign in."""
    await known.load()
    folder = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="lo9i-ssh-"))
    try:
        options = await asyncio.to_thread(_options, target, folder)
        try:
            connection = await asyncssh.connect(
                target.host, client_factory=lambda: _Client(known), known_hosts=asyncssh.SSHKnownHosts(), **options
            )
        except (OSError, asyncssh.Error) as e:
            raise MigrationError(said("Couldn't sign in to {host}: {error}", host=target.host, error=_why(e))) from e
    finally:
        await asyncio.to_thread(shutil.rmtree, folder, True)
    async with connection:
        yield connection


def _options(target: SshTarget, folder: Path) -> dict[str, Any]:
    options: dict[str, Any] = {"connect_timeout": _CONNECT_SECONDS, "keepalive_interval": _KEEPALIVE_SECONDS}
    if target.config:
        config = folder / "config"
        _write_private(config, target.config)
        options["config"] = [str(config)]
    if target.user:
        options["username"] = target.user
    if target.port:
        options["port"] = target.port
    if target.password:
        options["password"] = target.password
    if target.key_path:
        options["client_keys"] = [str(Path(target.key_path).expanduser())]
    if socket := agent_socket():
        options["agent_path"] = socket
    return options


def _why(error: Exception) -> str:
    if isinstance(error, asyncssh.HostKeyNotVerifiable):
        return said("its host key isn't the one known for it (in ~/.ssh/known_hosts or lo9i's own)")
    if isinstance(error, asyncssh.PermissionDenied):
        return said("it didn't accept the password or key")
    if isinstance(error, TimeoutError):
        return said("it didn't answer")
    return str(error) or type(error).__name__


def _write_private(path: Path, text: str) -> None:
    # Created readable only by the user, never readable by others even briefly.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(text)


def _append_private(path: Path, line: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a") as file:
        file.write(line)
