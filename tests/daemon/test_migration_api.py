"""Moving lo9i to another computer through the daemon: what `lo9i export` downloads, `lo9i import` uploads, and the
daemon restarts to move it into place (daemon/migration.py)."""

from pathlib import Path

import httpx
import pytest

from lo9i.client import DaemonClient
from lo9i.core.agent import HomeInUseError, MigrationError
from lo9i.core.migration import staging
from lo9i.daemon.api import create_app
from lo9i.daemon.auth import trusted
from lo9i.daemon.runs import RunHub
from lo9i.protocol import CLIENT_HEADER


class _Shutdown:
    def __init__(self) -> None:
        self.needed: list[str] = []

    def restart_needed(self, needed_by: str, by: str) -> int:
        self.needed.append(by)
        return 1


async def test_an_export_downloaded_comes_back_as_an_import_and_a_restart(service, isolated_settings: Path):
    (isolated_settings / "uploads").mkdir()
    (isolated_settings / "uploads" / "photo.txt").write_text("mine")
    shutdown = _Shutdown()
    transport = httpx.ASGITransport(app=trusted(create_app(service, RunHub(), shutdown=shutdown)))
    async with httpx.AsyncClient(transport=transport, base_url="http://lo9i", headers={CLIENT_HEADER: "t"}) as http:
        moving = DaemonClient(http).migration
        exported = isolated_settings.parent / "export.tar.gz.enc"
        with pytest.raises(MigrationError):
            await moving.export_to(exported, "short")
        assert not exported.exists()
        await moving.export_to(exported, "a long password")
        with pytest.raises(HomeInUseError):
            await moving.import_from(exported, "a long password")
        with pytest.raises(MigrationError):
            await moving.import_from(exported, "another password", replace=True)
        report = await moving.import_from(exported, "a long password", replace=True)

    assert report.waiting_for_runs == 1 and shutdown.needed == ["an import"]
    assert (isolated_settings / staging.STAGED / "home" / "uploads" / "photo.txt").read_text() == "mine"
