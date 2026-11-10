"""Moving lo9i to another computer over HTTP (core/migration/): the export, written to a temporary file and then
downloaded by a link that works once (so a browser saves it to disk as it comes, never holding it whole), the import,
uploaded and staged, then moved into place by a restart that waits for the runs in progress and can't be taken back,
and a move straight to another computer over SSH (daemon/moves.py)."""

import asyncio
import secrets
import shutil
import tempfile
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from lo9i.core.agent import AssistantService, HomeInUseError, ImportReport, MigrationError, MoveStatus, SavedHost
from lo9i.core.i18n import Texts, message, said
from lo9i.core.mcp.ssh_hosts import SshHostsError
from lo9i.core.migration.ssh import SshTarget
from lo9i.daemon import lo9i_copy, updates
from lo9i.daemon.moves import MoveRunningError, Moves
from lo9i.protocol import LANGUAGE_HEADER

# Where an export is downloaded from: a browser goes there itself, without the client header (daemon/api.py).
EXPORTS = "/system/exports/"
# How long an export waits to be downloaded before it's deleted.
_KEPT_SECONDS = 15 * 60
# How the OpenAPI schema describes the download: a file.
_FILE: dict[int | str, dict[str, Any]] = {200: {"content": {"application/octet-stream": {}}}}


class ExportRequest(BaseModel):
    password: str


@dataclass(frozen=True)
class ExportReady:
    # Where to download it, once.
    url: str
    name: str


class MoveRequest(BaseModel):
    """A host typed in (`host`, with `user`, `port`, `password` and `key_path` as needed), or one a plugin keeps
    (`plugin` and `host`, its name there). `replace`: set aside the data lo9i has there."""

    host: str
    plugin: str = ""
    user: str = ""
    port: int = 0
    password: str = ""
    key_path: str = ""
    replace: bool = False


class _Exports:
    """Exports written and waiting to be downloaded, each by a token of its own, once."""

    def __init__(self) -> None:
        self._waiting: dict[str, Path] = {}

    def keep(self, export: Path) -> str:
        """`export` is alone in a folder of its own, deleted with it."""
        token = secrets.token_urlsafe(24)
        self._waiting[token] = export
        asyncio.get_running_loop().call_later(_KEPT_SECONDS, self._drop, token)
        return token

    def take(self, token: str) -> Path | None:
        """The export, whose folder the caller deletes; None for a token unknown, taken or expired."""
        return self._waiting.pop(token, None)

    def _drop(self, token: str) -> None:
        if (export := self._waiting.pop(token, None)) is not None:
            shutil.rmtree(export.parent, ignore_errors=True)


def add_migration_routes(app: FastAPI, service: AssistantService, shutdown: Any) -> None:
    """`shutdown` restarts the daemon to move an import into place (daemon/shutdown.py)."""
    _add_export_routes(app, service)
    _add_import_route(app, service, shutdown)
    _add_move_routes(app, service)


def _add_export_routes(app: FastAPI, service: AssistantService) -> None:
    exports = _Exports()

    @app.post("/system/export")
    async def export_data(body: ExportRequest) -> ExportReady:
        """lo9i's data, sealed with the password, written to a file to import on another computer, downloaded once
        from `url` within 15 minutes. 400: a password too short, or the data couldn't be read."""
        folder = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="lo9i-export-"))
        out = folder / export_name()
        try:
            await service.export_data(out, body.password)
        except (MigrationError, OSError) as e:
            await asyncio.to_thread(shutil.rmtree, folder, True)
            raise HTTPException(400, message(e)) from e
        return ExportReady(EXPORTS + exports.keep(out), out.name)

    @app.get(EXPORTS + "{token}", response_class=FileResponse, responses=_FILE)
    async def download_export(token: str) -> FileResponse:
        """The export, once. 404: an unknown token, or one used or expired."""
        out = exports.take(token)
        if out is None:
            raise HTTPException(404, said("This export was downloaded already, or expired: export again."))
        removed = BackgroundTask(shutil.rmtree, out.parent, ignore_errors=True)
        return FileResponse(out, media_type="application/octet-stream", filename=out.name, background=removed)


def _add_import_route(app: FastAPI, service: AssistantService, shutdown: Any) -> None:
    @app.post("/system/import")
    async def import_data(
        request: Request,
        file: Annotated[UploadFile, File()],
        password: Annotated[str, Form()],
        replacing: Annotated[bool, Form(alias="replace")] = False,
    ) -> ImportReport:
        """Stages an export for the daemon's next start, which this asks for: what lo9i has here is set aside in a
        folder beside its own, never deleted. 409: lo9i has data here and `replace` is false. 400: a wrong password,
        or the file isn't an export or is damaged."""
        try:
            report = await service.stage_import(file.file, password, replacing)
        except HomeInUseError as e:
            raise HTTPException(409, message(e)) from e
        except (MigrationError, OSError) as e:
            raise HTTPException(400, message(e)) from e
        waiting = shutdown.restart_needed(said("An import is waiting to be moved into place"), "an import")
        return (await _texts(service, request)).within(replace(report, waiting_for_runs=waiting))


def _add_move_routes(app: FastAPI, service: AssistantService) -> None:
    moves = Moves(service, service.bus.publish, _write_lo9i_copy)

    @app.get("/system/move")
    async def move_status(request: Request) -> MoveStatus:
        """The move running, or the last one; `state` is "" when there was none. A `move` event says it changed."""
        return (await _texts(service, request)).within(moves.status())

    @app.post("/system/move")
    async def start_move(request: Request, body: MoveRequest) -> MoveStatus:
        """Starts moving lo9i to another computer over SSH, in the background. 409: one is running. 400: a plugin's
        host that can't be read."""
        try:
            status = moves.start(await _target(service, body), _named(body), body.replace)
        except MoveRunningError as e:
            raise HTTPException(409, message(e)) from e
        return (await _texts(service, request)).within(status)

    @app.delete("/system/move")
    async def cancel_move(request: Request) -> MoveStatus:
        """Cancels the move running; the copied file is deleted there. 409: none is running."""
        if not moves.cancel():
            raise HTTPException(409, said("No move is running."))
        return (await _texts(service, request)).within(moves.status())

    @app.get("/system/move/hosts")
    async def move_hosts() -> list[SavedHost]:
        """The SSH hosts plugins keep (core/mcp/ssh_hosts.py), without how to sign in to them."""
        return await service.ssh_hosts.every()


async def _target(service: AssistantService, body: MoveRequest) -> SshTarget:
    """Raises HTTPException 400 for no host, or a plugin's that can't be read."""
    if not body.host.strip():
        raise HTTPException(400, said("Say which computer to move to."))
    if not body.plugin:
        return SshTarget(body.host.strip(), body.user.strip(), body.port, body.password, body.key_path.strip())
    try:
        found = await service.ssh_hosts.connection(body.plugin, body.host)
    except SshHostsError as e:
        raise HTTPException(400, message(e)) from e
    return SshTarget(body.host, password=found.password, config=found.config)


def _named(body: MoveRequest) -> str:
    """The host as the user knows it."""
    if body.plugin:
        return body.host
    user = f"{body.user.strip()}@" if body.user.strip() else ""
    return f"{user}{body.host.strip()}{f':{body.port}' if body.port else ''}"


async def _write_lo9i_copy(out: Path) -> None:
    root = updates.repository_root()
    await asyncio.to_thread(lo9i_copy.write, root, out, await updates.version_of(root))


async def _texts(service: AssistantService, request: Request) -> Texts:
    return await service.texts(request.headers.get(LANGUAGE_HEADER))


def export_name() -> str:
    return f"lo9i-export-{date.today().isoformat()}.tar.gz.enc"
