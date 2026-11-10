"""Moving lo9i to another computer over SSH, from the apps (Settings → System's Move to another computer, `lo9i
migrate`): one move at a time, in the background, its progress a `move` event the apps answer by asking for its
status (`GET /system/move`). It signs in (core/migration/ssh.py), installs lo9i there from a copy of this one when
it's missing (lo9i_copy.py, install.sh), exports with a key made for this move alone, copies the export there,
imports it with lo9i's own command, which waits for that lo9i to restart with it, and deletes the copied file, also
when something fails or the move is cancelled. The export never leaves this computer but sealed, and its key goes
only to the import's input."""

import asyncio
import logging
import secrets
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from lo9i.core.i18n import message, said
from lo9i.core.migration import ImportReport
from lo9i.core.migration import moving as steps
from lo9i.core.migration.errors import MigrationError
from lo9i.core.migration.moving import MoveStatus
from lo9i.core.migration.remote import RemoteInfo, ssh_remote
from lo9i.core.migration.ssh import SshTarget

logger = logging.getLogger(__name__)

EVENT = "move"
# What the export and the copy of lo9i need there, as a share of the export's size: the file, and it unpacked.
_ROOM = 3
# Progress is told at most this often; a step's start and end, always.
_TELL_SECONDS = 0.5
_MB = 1_000_000


class MoveRunningError(Exception):
    """A move is running already."""


class Remote(Protocol):
    """The other computer (core/migration/remote.py's SshRemote)."""

    trusted_now: str

    async def probe(self) -> RemoteInfo: ...

    async def upload(self, local: Path, name: str, progress: Callable[[int, int], None]) -> str: ...

    async def install(self, payload: str, said_line: Callable[[str], None]) -> str: ...

    async def import_export(self, lo9i: str, export: str, key: str, replace: bool) -> ImportReport: ...

    async def remove(self, path: str) -> None: ...


class Exporting(Protocol):
    """What moves needs of the service: the export (core/agent/migration.py), and telling the apps."""

    async def export_data(self, out: Path, password: str, written: Callable[[int], None] | None = None) -> Any: ...


Opener = Callable[[SshTarget], AbstractAsyncContextManager[Remote]]


class Moves:
    def __init__(
        self,
        service: Exporting,
        publish: Callable[[str], None],
        lo9i_copy: Callable[[Path], Awaitable[None]],
        open_remote: Opener = ssh_remote,
    ) -> None:
        """`lo9i_copy` writes a copy of this lo9i to install there (lo9i_copy.py)."""
        self._service = service
        self._publish = publish
        self._lo9i_copy = lo9i_copy
        self._open = open_remote
        self._status = MoveStatus()
        self._task: asyncio.Task[None] | None = None
        self._told = 0.0

    def status(self) -> MoveStatus:
        return self._status

    def start(self, target: SshTarget, host: str, replace_data: bool) -> MoveStatus:
        """Starts moving to `target`, named `host` to the user. Raises MoveRunningError."""
        if self._task is not None and not self._task.done():
            raise MoveRunningError(said("A move is running already."))
        self._status = steps.started(host)
        self._task = asyncio.create_task(self._run(target, replace_data), name="move")
        self._tell(force=True)
        return self._status

    async def until_ended(self) -> MoveStatus:
        """Waits for the move running, if one is, to end; its status then."""
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)
        return self._status

    def cancel(self) -> bool:
        """False when no move is running."""
        if self._task is None or self._task.done():
            return False
        self._task.cancel()
        return True

    async def _run(self, target: SshTarget, replace_data: bool) -> None:
        scratch = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="lo9i-move-"))
        try:
            report = await self._move(target, replace_data, scratch)
            self._status = replace(self._status, state="done", progress=-1, to_redo=report.to_redo)
        except MigrationError as e:
            self._failed(message(e))
        except asyncio.CancelledError:
            self._failed(said("Cancelled."), state="cancelled")
            raise
        except Exception as e:
            logger.exception("The move to %s failed", self._status.host)
            self._failed(str(e) or type(e).__name__)
        finally:
            await asyncio.to_thread(shutil.rmtree, scratch, True)
            self._tell(force=True)

    async def _move(self, target: SshTarget, replace_data: bool, scratch: Path) -> ImportReport:
        self._begin(steps.CONNECT)
        async with self._open(target) as remote:
            info = await remote.probe()
            self._end(steps.CONNECT, _trusted(remote.trusted_now))
            lo9i, installed = await self._installed(remote, info, scratch)
            key = secrets.token_urlsafe(32)
            export = await self._export(scratch, key, info)
            copied = await self._copy(remote, export, f".lo9i-move-{secrets.token_hex(6)}.tar.gz.enc")
            try:
                report = await self._import(remote, lo9i, copied, key, replace_data)
            finally:
                await self._clean(remote, copied)
        return replace(report, to_redo=[*report.to_redo, *([_COPIED] if installed else [])])

    async def _installed(self, remote: Remote, info: RemoteInfo, scratch: Path) -> tuple[str, bool]:
        """Its lo9i command, and whether it was installed now."""
        self._begin(steps.INSTALL)
        if info.lo9i:
            if not info.imports:
                raise MigrationError(said("lo9i there is older than this one and can't import: update it there first."))
            self._end(steps.INSTALL, said("lo9i is installed there already."), "skipped")
            return info.lo9i, False
        _check_installable(info)
        payload = scratch / "lo9i.tar.gz"
        await self._lo9i_copy(payload)
        copied = await remote.upload(payload, f".lo9i-install-{secrets.token_hex(6)}.tar.gz", self._copied)
        self._status.progress = -1
        lo9i = await remote.install(copied, lambda line: self._detail(steps.INSTALL, line))
        if not lo9i:
            raise MigrationError(said("install.sh ran there, but lo9i's command isn't where it puts it."))
        self._end(steps.INSTALL, "")
        return lo9i, True

    async def _export(self, scratch: Path, key: str, info: RemoteInfo) -> Path:
        self._begin(steps.EXPORT)
        out = scratch / "export.tar.gz.enc"
        loop = asyncio.get_running_loop()

        def written(size: int) -> None:
            # Told from the thread writing the export.
            loop.call_soon_threadsafe(self._written, size)

        await self._service.export_data(out, key, written)
        size = (await asyncio.to_thread(out.stat)).st_size
        if info.free_bytes and size * _ROOM > info.free_bytes:
            raise MigrationError(
                said(
                    "There isn't room there: the export takes {needed} MB, and it has {free} MB free.",
                    needed=size * _ROOM // _MB,
                    free=info.free_bytes // _MB,
                )
            )
        self._end(steps.EXPORT, said("{size} MB", size=size // _MB))
        return out

    async def _copy(self, remote: Remote, export: Path, name: str) -> str:
        self._begin(steps.COPY)
        copied = await remote.upload(export, name, self._copied)
        self._end(steps.COPY, "")
        return copied

    async def _import(self, remote: Remote, lo9i: str, copied: str, key: str, replace_data: bool) -> ImportReport:
        self._begin(steps.IMPORT)
        report = await remote.import_export(lo9i, copied, key, replace_data)
        self._end(steps.IMPORT, "")
        return report

    async def _clean(self, remote: Remote, copied: str) -> None:
        """Runs however the import ended, cancelled too: the copy, sealed or not, doesn't stay there."""
        self._begin(steps.CLEAN)
        try:
            await asyncio.shield(remote.remove(copied))
        except Exception as e:
            self._end(steps.CLEAN, said("Delete {path} there: {error}", path=copied, error=e), "failed")
            return
        self._end(steps.CLEAN, "")

    def _begin(self, key: str) -> None:
        self._step(key).state = "running"
        self._status.progress = -1
        self._tell(force=True)

    def _end(self, key: str, detail: str, state: str = "done") -> None:
        step = self._step(key)
        step.state, step.detail = state, detail
        self._status.progress = -1
        self._tell(force=True)

    def _detail(self, key: str, detail: str) -> None:
        self._step(key).detail = detail
        self._tell()

    def _written(self, written: int) -> None:
        self._detail(steps.EXPORT, said("{size} MB written", size=written // _MB))

    def _copied(self, done: int, total: int) -> None:
        self._status.progress = done / total if total else -1
        running = next((s for s in self._status.steps if s.state == "running"), None)
        if running is not None:
            self._detail(running.key, said("{done} of {total} MB", done=done // _MB, total=total // _MB))

    def _failed(self, error: str, state: str = "failed") -> None:
        for step in self._status.steps:
            if step.state == "running":
                step.state = "failed"
        self._status = replace(self._status, state=state, error=error, progress=-1)

    def _step(self, key: str) -> steps.MoveStep:
        return next(s for s in self._status.steps if s.key == key)

    def _tell(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._told >= _TELL_SECONDS:
            self._told = now
            self._publish(EVENT)


_COPIED = said(
    "lo9i was installed there from this computer's copy, which its app can't update: install it there with "
    "install.sh from lo9i's repository when you want updates from the app."
)


def _trusted(fingerprint: str) -> str:
    if not fingerprint:
        return ""
    return said("First connection: its host key {fingerprint} is kept as the one to expect.", fingerprint=fingerprint)


def _check_installable(info: RemoteInfo) -> None:
    if info.system not in ("Linux", "Darwin"):
        raise MigrationError(said("lo9i installs on Linux and macOS; this host runs {system}.", system=info.system))
    if info.folder:
        raise MigrationError(
            said("~/lo9i-assistant is there, but lo9i isn't installed from it: install it there or move it away.")
        )
    if info.missing:
        raise MigrationError(said("Installing lo9i there needs {missing}.", missing=", ".join(info.missing)))
