from pathlib import Path

import httpx

from lo9i.client.daemon_client.transport import Transport
from lo9i.core.agent import HomeInUseError, ImportReport, MigrationError

# Writing or reading an export of a few gigabytes takes as long as it takes.
_LONG = httpx.Timeout(None, connect=5)


class MigrationApi:
    """Moving lo9i to another computer: an export of its data, sealed with a password, and an import of one, which
    the daemon moves into place when it restarts (core/migration/)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def export_to(self, target: Path, password: str) -> None:
        """Writes the export to `target`, removed again if it fails. Raises MigrationError (a password too short)."""
        try:
            with target.open("wb") as out:
                await self._transport.download(
                    "/system/export", out, json={"password": password}, errors={400: MigrationError}, timeout=_LONG
                )
        except BaseException:
            target.unlink(missing_ok=True)
            raise

    async def import_from(self, source: Path, password: str, replace: bool = False) -> ImportReport:
        """Stages the export for the daemon's next start, which it restarts for once no run is in progress. Raises
        HomeInUseError when lo9i has data here and `replace` is false, MigrationError when the export can't be opened
        (a wrong password, a damaged file)."""
        with source.open("rb") as file:
            report = await self._transport.request(
                "POST",
                "/system/import",
                files={"file": (source.name, file, "application/octet-stream")},
                data={"password": password, "replace": "true" if replace else "false"},
                errors={400: MigrationError, 409: HomeInUseError},
                timeout=_LONG,
            )
        return ImportReport(**report)
