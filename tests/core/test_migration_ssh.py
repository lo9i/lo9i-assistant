"""Moving lo9i over SSH, against an SSH server of the test's own (asyncssh's): signing in with a password, a host met
the first time trusted and its key kept, a key that changes refused, and the other computer's file operations."""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncssh
import pytest

from lo9i.core.migration import MigrationError
from lo9i.core.migration.remote import ssh_remote
from lo9i.core.migration.ssh import SshTarget

USER, PASSWORD = "me", "its password"


class _Server(asyncssh.SSHServer):
    def begin_auth(self, username: str) -> bool:
        return True

    def password_auth_supported(self) -> bool:
        return True

    def validate_password(self, username: str, password: str) -> bool:
        return (username, password) == (USER, PASSWORD)


def _runs_in(home: Path):
    async def run(process: asyncssh.SSHServerProcess) -> None:
        child = await asyncio.create_subprocess_shell(
            str(process.command),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "HOME": str(home)},
        )
        out, err = await child.communicate(str(await process.stdin.read()).encode())
        process.stdout.write(out.decode())
        process.stderr.write(err.decode())
        process.exit(child.returncode or 0)

    return run


async def _server(home: Path, key: asyncssh.SSHKey) -> asyncssh.SSHAcceptor:
    return await asyncssh.create_server(
        _Server, "127.0.0.1", 0, server_host_keys=[key], process_factory=_runs_in(home), sftp_factory=True
    )


@pytest.fixture
async def there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[Path, int, asyncssh.SSHKey]]:
    """The other computer's home folder (the SFTP server's folder), its port and host key; this one's own home folder
    has no ssh files."""
    monkeypatch.setenv("HOME", str(tmp_path / "here"))
    monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
    home = tmp_path / "there"
    home.mkdir()
    monkeypatch.chdir(home)
    key = asyncssh.generate_private_key("ssh-ed25519")
    server = await _server(home, key)
    yield home, server.sockets[0].getsockname()[1], key
    server.close()


async def test_a_host_met_the_first_time_is_trusted_and_its_files_handled(there):
    home, port, key = there
    target = SshTarget("127.0.0.1", USER, port, PASSWORD)
    local = home.parent / "export"
    local.write_bytes(b"sealed")
    sizes: list[int] = []

    async with ssh_remote(target) as remote:
        info = await remote.probe()
        copied = await remote.upload(local, "copied", lambda done, total: sizes.append(done))
        assert Path(copied).read_bytes() == b"sealed" and oct(Path(copied).stat().st_mode & 0o777) == "0o600"
        await remote.remove(copied)

    assert remote.trusted_now == key.get_fingerprint()
    assert info.system == os.uname().sysname and info.lo9i == "" and info.free_bytes > 0
    assert sizes[-1] == len(b"sealed") and not Path(copied).exists()
    async with ssh_remote(target) as again:
        assert again.trusted_now == ""


async def test_a_host_key_that_changed_is_refused(there, isolated_settings: Path):
    _, port, key = there
    target = SshTarget("127.0.0.1", USER, port, PASSWORD)
    async with ssh_remote(target):
        pass
    kept = isolated_settings / "keys" / "known_hosts"
    other = asyncssh.generate_private_key("ssh-ed25519").export_public_key().decode().strip()
    kept.write_text(kept.read_text().replace(key.export_public_key().decode().strip(), other))

    with pytest.raises(MigrationError, match="host key"):
        async with ssh_remote(target):
            pass


async def test_a_wrong_password_is_said(there):
    _, port, _ = there
    with pytest.raises(MigrationError, match="didn't accept"):
        async with ssh_remote(SshTarget("127.0.0.1", USER, port, "not it")):
            pass
