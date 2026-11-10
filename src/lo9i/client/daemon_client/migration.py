from pathlib import Path
from typing import Any

import httpx

from lo9i.client.daemon_client.transport import Transport
from lo9i.core.agent import HomeInUseError, ImportReport, MigrationError, MoveStatus, MoveStep, SavedHost

# Writing or reading an export of a few gigabytes takes as long as it takes.
_LONG = httpx.Timeout(None, connect=5)


class MoveRunningError(Exception):
    """A move is running already."""


class NoMoveError(Exception):
    """No move is running to cancel."""


class MigrationApi:
    """Moving lo9i to another computer: an export of its data, sealed with a password, an import of one, which the
    daemon moves into place when it restarts (core/migration/), and a move straight to another computer over SSH
    (daemon/moves.py)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def export_to(self, target: Path, password: str) -> None:
        """Writes the export to `target`, removed again if it fails. Raises MigrationError (a password too short)."""
        ready = await self._transport.request(
            "POST", "/system/export", json={"password": password}, errors={400: MigrationError}, timeout=_LONG
        )
        try:
            with target.open("wb") as out:
                await self._transport.download(ready["url"], out, errors={404: MigrationError}, timeout=_LONG)
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

    async def saved_hosts(self) -> list[SavedHost]:
        """The SSH hosts plugins keep (the hosts plugin's)."""
        return [SavedHost(**h) for h in await self._transport.request("GET", "/system/move/hosts")]

    async def move(self, host: str, *, plugin: str = "", replace: bool = False, **signing_in: Any) -> MoveStatus:
        """Starts moving to `host`: a plugin's host by its name there, or an address with `user`, `port`, `password`
        and `key_path` as needed. A `move` event says how it goes. Raises MoveRunningError, MigrationError (a plugin's
        host that can't be read)."""
        body = {"host": host, "plugin": plugin, "replace": replace, **signing_in}
        errors = {409: MoveRunningError, 400: MigrationError}
        return _status(await self._transport.request("POST", "/system/move", json=body, errors=errors))

    async def move_status(self) -> MoveStatus:
        return _status(await self._transport.request("GET", "/system/move"))

    async def cancel_move(self) -> MoveStatus:
        """Raises NoMoveError."""
        return _status(await self._transport.request("DELETE", "/system/move", errors={409: NoMoveError}))


def _status(data: dict[str, Any]) -> MoveStatus:
    steps = [MoveStep(**s) for s in data.pop("steps", [])]
    return MoveStatus(**data, steps=steps)
