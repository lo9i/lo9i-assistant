"""Moving lo9i to another computer (core/migration/): an export of its data home, sealed with a password, and an
import of one, staged for the next start, which moves it into place and then builds plugins' environments again."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, cast

from lo9i.core.agent.base import ServiceBase
from lo9i.core.i18n import said
from lo9i.core.mcp import servers
from lo9i.core.mcp.servers import McpServer, McpServerError
from lo9i.core.mcp.ssh_hosts import SavedHost
from lo9i.core.migration import (
    HomeInUseError,
    ImportReport,
    MigrationError,
    WrongPasswordError,
    check_password,
    data_here,
    export,
    staging,
)
from lo9i.core.migration.home import home
from lo9i.core.migration.manifest import HOME, Manifest
from lo9i.core.migration.moving import MoveStatus, MoveStep
from lo9i.core.migration.to_redo import to_redo

__all__ = [
    "HomeInUseError",
    "ImportReport",
    "MigrationError",
    "MigrationMixin",
    "MoveStatus",
    "MoveStep",
    "SavedHost",
    "WrongPasswordError",
]

logger = logging.getLogger(__name__)


class MigrationMixin(ServiceBase):
    async def export_data(self, out: Path, password: str, written: Callable[[int], None] | None = None) -> Manifest:
        """Writes the export to `out`. `written` is told the bytes written so far, from the thread writing them.
        Raises MigrationError: a password too short, lo9i.db that can't be copied."""
        check_password(password)
        return await asyncio.to_thread(_write, out, password, written or (lambda _: None))

    async def stage_import(self, source: BinaryIO, password: str, replace: bool) -> ImportReport:
        """Stages the export in `source` for the next start. Raises HomeInUseError when this computer has data of
        its own and `replace` is false (with it, the next start sets that data aside), MigrationError when the export
        can't be opened (WrongPasswordError)."""
        if not replace and (found := await self._data_here()):
            raise HomeInUseError(
                said(
                    "lo9i on this computer already has data ({found}). Import replacing it: it's kept in a folder "
                    "beside lo9i's.",
                    found=", ".join(found),
                )
            )
        where, user_home = home(), Path.home()
        manifest = await asyncio.to_thread(staging.stage, source, password, where, user_home)
        items = await asyncio.to_thread(to_redo, manifest, where / staging.STAGED / HOME, user_home)
        return ImportReport(manifest.host, manifest.system, manifest.exported_at, items)

    async def settle_import(self) -> None:
        """After a start that moved an import into place: builds each plugin's environment, which the export leaves
        out, as installing the plugin does. One that fails is logged; its next start tries again."""
        for server in await servers.load_all(self._storage.store):
            try:
                for command in _commands(server):
                    await self._environments.ensure(server.name, command)
            except McpServerError as e:
                logger.warning("Couldn't install what %s needs after the import: %s", server.name, e)

    async def _data_here(self) -> list[str]:
        found = await asyncio.to_thread(data_here, home())
        # Read to its end: listing holds the checkpointer's lock until it ends.
        written = [c async for c in self._storage.checkpointer.alist(None, limit=1)]
        return ["conversations", *found] if written else found


def _write(out: Path, password: str, written: Callable[[int], None]) -> Manifest:
    with out.open("wb") as f:
        return export.write(home(), cast(BinaryIO, _Counted(f, written)), password)


class _Counted:
    """A file that says how much was written to it."""

    def __init__(self, file: BinaryIO, written: Callable[[int], None]) -> None:
        self._file = file
        self._written = written
        self._count = 0

    def write(self, data: bytes) -> int:
        self._count += self._file.write(data)
        self._written(self._count)
        return len(data)


def _commands(server: McpServer) -> list[str]:
    """What it runs; `ensure` builds the environment for the first that runs from it."""
    commands = [server.command, server.page_command, server.channel_command, server.agent_worker, server.check_command]
    return [c for c in commands if c]
