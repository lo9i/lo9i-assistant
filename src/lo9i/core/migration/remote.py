"""What moving lo9i does on the other computer, over an SSH connection (ssh.py): finding out what it has, installing
lo9i from a copy of this one, copying a file there, importing it with lo9i's own command, deleting a file. Commands go
to the host's `sh`, with every path quoted; lo9i's command is run by its full path, since a command run over SSH
reads no profile that would put it on PATH."""

import contextlib
import json
import logging
import shlex
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path

import asyncssh

from lo9i.core.i18n import said
from lo9i.core.migration import ImportReport
from lo9i.core.migration.errors import HomeInUseError, MigrationError
from lo9i.core.migration.ssh import KnownHosts, SshTarget, connected

logger = logging.getLogger(__name__)

# Where lo9i is installed there, as install.sh does when it's piped: in the user's home.
FOLDER = "lo9i-assistant"
# What `lo9i import` exits with when lo9i has data there (clients/terminal's migration_command.py).
HOME_IN_USE = 3
_NEEDED = ("bash", "git", "curl", "tar")
_PROBE = f"""
echo "system=$(uname -s)"
echo "machine=$(uname -m)"
for c in "$HOME/.local/bin/lo9i" "$HOME/{FOLDER}/.venv/bin/lo9i"; do
  if [ -x "$c" ]; then
    echo "lo9i=$c"
    "$c" import --help 2>/dev/null | grep -q -- --password-stdin && echo imports=1
    break
  fi
done
[ -e "$HOME/{FOLDER}" ] && echo folder=1
echo "free=$(df -Pk "$HOME" | awk 'NR==2 {{print $4}}')"
for t in {" ".join(_NEEDED)}; do command -v "$t" >/dev/null 2>&1 || echo "missing=$t"; done
"""


@dataclass(frozen=True)
class RemoteInfo:
    system: str = ""
    machine: str = ""
    # Its lo9i command's path; "" when lo9i isn't installed.
    lo9i: str = ""
    # Its lo9i is new enough to import an export it's given on its input.
    imports: bool = False
    # ~/lo9i-assistant is there without lo9i installed from it.
    folder: bool = False
    free_bytes: int = 0
    # What installing lo9i needs that it doesn't have.
    missing: list[str] = field(default_factory=list)


def parse_probe(output: str) -> RemoteInfo:
    values: dict[str, list[str]] = {}
    for line in output.splitlines():
        key, _, value = line.partition("=")
        values.setdefault(key.strip(), []).append(value.strip())
    first = {k: v[0] for k, v in values.items()}
    free = first.get("free", "")
    return RemoteInfo(
        system=first.get("system", ""),
        machine=first.get("machine", ""),
        lo9i=first.get("lo9i", ""),
        imports="imports" in first,
        folder="folder" in first and "lo9i" not in first,
        free_bytes=int(free) * 1024 if free.isdigit() else 0,
        missing=values.get("missing", []),
    )


@contextlib.asynccontextmanager
async def ssh_remote(target: SshTarget) -> AsyncIterator["SshRemote"]:
    """Signs in to the other computer (ssh.py). Raises MigrationError."""
    known = KnownHosts.lo9i()
    async with connected(target, known) as connection:
        yield SshRemote(connection, await known.remember())


class SshRemote:
    """The other computer, over an open connection."""

    def __init__(self, connection: asyncssh.SSHClientConnection, trusted_now: str = "") -> None:
        self._connection = connection
        # The fingerprint of its host key when lo9i met it for the first time now; "" when it was known.
        self.trusted_now = trusted_now

    async def probe(self) -> RemoteInfo:
        result = await self._connection.run(_PROBE, check=False, stdin=asyncssh.DEVNULL)
        return parse_probe(str(result.stdout or ""))

    async def upload(self, local: Path, name: str, progress: Callable[[int, int], None]) -> str:
        """Copies `local` to `name` in the user's home there, readable only by them; returns its path there."""
        async with self._connection.start_sftp_client() as sftp:
            home = await sftp.realpath(".")
            remote = f"{home}/{name}"
            async with sftp.open(remote, "wb", asyncssh.SFTPAttrs(permissions=0o600)):
                pass
            await sftp.put(str(local), remote, progress_handler=lambda _a, _b, done, total: progress(done, total))
        return remote

    async def install(self, payload: str, said_line: Callable[[str], None]) -> str:
        """Installs lo9i from the copy at `payload`, which it deletes, with install.sh. Returns lo9i's command there.
        Each line install.sh writes goes to `said_line`."""
        script = (
            f'set -e; cd "$HOME"; mkdir -p {FOLDER}; tar -xzf {shlex.quote(payload)} -C {FOLDER}; '
            f"rm -f {shlex.quote(payload)}; cd {FOLDER}; ./install.sh --model-later"
        )
        lines: list[str] = []
        async with self._connection.create_process(script, stdin=asyncssh.DEVNULL, stderr=asyncssh.STDOUT) as process:
            async for line in process.stdout:
                if line.strip():
                    lines.append(line.strip())
                    said_line(line.strip())
            await process.wait()
        if process.exit_status != 0:
            raise MigrationError(said("Installing lo9i there failed: {error}", error=lines[-1] if lines else "?"))
        return (await self.probe()).lo9i

    async def import_export(self, lo9i: str, export: str, key: str, replace: bool) -> ImportReport:
        """Runs `lo9i import` there, which waits for its daemon to restart with the import. Raises HomeInUseError
        when lo9i has data there and `replace` is false."""
        command = [lo9i, "import", export, "--password-stdin", "--json", "--wait", *(["--force"] if replace else [])]
        result = await self._connection.run(shlex.join(command), input=key + "\n", check=False)
        if result.exit_status == HOME_IN_USE:
            raise HomeInUseError(_last_line(result.stderr))
        if result.exit_status != 0:
            raise MigrationError(said("The import there failed: {error}", error=_last_line(result.stderr)))
        try:
            return ImportReport(**json.loads(str(result.stdout)))
        except (ValueError, TypeError) as e:
            raise MigrationError(said("The import there answered in a form lo9i can't read.")) from e

    async def remove(self, path: str) -> None:
        await self._connection.run(f"rm -f {shlex.quote(path)}", check=False, stdin=asyncssh.DEVNULL)


def _last_line(text: object) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return lines[-1] if lines else "?"
