"""Moving lo9i straight to another computer (daemon/moves.py): signed in, lo9i installed there when it's missing, the
export copied there and imported, and the copy deleted there whatever happens, with a fake for the other computer
that imports into a data home of its own."""

import asyncio
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from lo9i.core.agent import AssistantService, ImportReport, MigrationError
from lo9i.core.migration import staging
from lo9i.core.migration.remote import RemoteInfo
from lo9i.core.migration.ssh import SshTarget
from lo9i.daemon.moves import Moves


class _There:
    """The other computer: a home folder holding lo9i's data home, and what was done there."""

    def __init__(self, user: Path, info: RemoteInfo, import_fails: bool = False) -> None:
        self.user = user
        self.info = info
        self.import_fails = import_fails
        self.trusted_now = "SHA256:fake"
        self.installed_from = b""
        self.removed: list[str] = []
        (user / ".lo9i").mkdir(parents=True)

    async def probe(self) -> RemoteInfo:
        return self.info

    async def upload(self, local: Path, name: str, progress) -> str:
        copied = self.user / name
        shutil.copyfile(local, copied)
        progress(copied.stat().st_size, copied.stat().st_size)
        return str(copied)

    async def install(self, payload: str, said_line) -> str:
        self.installed_from = Path(payload).read_bytes()
        Path(payload).unlink()
        said_line("Installing the Python dependencies")
        return f"{self.user}/.local/bin/lo9i"

    async def import_export(self, lo9i: str, export: str, key: str, replace: bool) -> ImportReport:
        if self.import_fails:
            raise MigrationError("The import there failed: disk full")
        with open(export, "rb") as source:
            manifest = staging.stage(source, key, self.user / ".lo9i", self.user)
        return ImportReport(manifest.host, manifest.system, manifest.exported_at, ["Turn on Start at boot again."])

    async def remove(self, path: str) -> None:
        self.removed.append(path)
        Path(path).unlink(missing_ok=True)


def _moves(service: AssistantService, there: _There, told: list[str]) -> Moves:
    @asynccontextmanager
    async def signed_in(target: SshTarget) -> AsyncIterator[_There]:
        yield there

    async def lo9i_copy(out: Path) -> None:
        out.write_bytes(b"lo9i itself")

    return Moves(service, told.append, lo9i_copy, signed_in)


async def test_a_move_installs_lo9i_there_imports_the_export_and_deletes_its_copy(
    service: AssistantService, isolated_settings: Path
):
    (isolated_settings / "uploads").mkdir()
    (isolated_settings / "uploads" / "photo.txt").write_text("mine")
    there, told = _There(isolated_settings / "there", RemoteInfo("Linux", "x86_64", free_bytes=1 << 40)), []
    moves = _moves(service, there, told)

    moves.start(SshTarget("there"), "me@there", False)
    status = await asyncio.wait_for(moves.until_ended(), 30)

    assert status.state == "done", status.error
    assert {s.key: s.state for s in status.steps} == {
        "connect": "done",
        "install": "done",
        "export": "done",
        "copy": "done",
        "import": "done",
        "clean": "done",
    }
    assert there.installed_from == b"lo9i itself"
    assert (there.user / ".lo9i" / staging.STAGED / "home" / "uploads" / "photo.txt").read_text() == "mine"
    assert len(there.removed) == 1 and not Path(there.removed[0]).exists()
    assert status.to_redo[0] == "Turn on Start at boot again." and len(status.to_redo) == 2
    assert "SHA256:fake" in status.steps[0].detail and told


async def test_a_failed_import_still_deletes_the_copy_and_says_why(service: AssistantService, isolated_settings: Path):
    info = RemoteInfo("Linux", "x86_64", lo9i="/home/me/.local/bin/lo9i", imports=True)
    there = _There(isolated_settings / "there", info, import_fails=True)
    moves = _moves(service, there, [])

    moves.start(SshTarget("there"), "there", False)
    status = await asyncio.wait_for(moves.until_ended(), 30)

    assert status.state == "failed" and "disk full" in status.error
    states = {s.key: s.state for s in status.steps}
    assert states["install"] == "skipped" and states["import"] == "failed" and states["clean"] == "done"
    assert len(there.removed) == 1 and not list(there.user.glob(".lo9i-move-*"))


@pytest.mark.parametrize(
    ("info", "why"),
    [
        (RemoteInfo("Linux", "x86_64", lo9i="/x/lo9i", imports=False), "older"),
        (RemoteInfo("Linux", "x86_64", missing=["git"]), "git"),
    ],
)
async def test_a_host_lo9i_cant_move_to_stops_before_exporting(
    service: AssistantService, isolated_settings: Path, info: RemoteInfo, why: str
):
    there = _There(isolated_settings / "there", info)
    moves = _moves(service, there, [])

    moves.start(SshTarget("there"), "there", False)
    status = await asyncio.wait_for(moves.until_ended(), 30)

    assert status.state == "failed" and why in status.error
    assert {s.key: s.state for s in status.steps}["export"] == "waiting"
