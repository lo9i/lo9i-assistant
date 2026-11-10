"""Moving lo9i to another computer over HTTP (core/migration/): the export, written to a temporary file and sent as the
answer, and the import, uploaded and staged, then moved into place by a restart that waits for the runs in progress
and can't be taken back."""

import shutil
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from lo9i.core.agent import AssistantService, HomeInUseError, ImportReport, MigrationError
from lo9i.core.i18n import message, said
from lo9i.protocol import LANGUAGE_HEADER

# How the OpenAPI schema describes the export: a file.
_FILE: dict[int | str, dict[str, Any]] = {200: {"content": {"application/octet-stream": {}}}}


class ExportRequest(BaseModel):
    password: str


def add_migration_routes(app: FastAPI, service: AssistantService, shutdown: Any) -> None:
    """`shutdown` restarts the daemon to move an import into place (daemon/shutdown.py)."""

    @app.post("/system/export", response_class=FileResponse, responses=_FILE)
    async def export_data(body: ExportRequest) -> FileResponse:
        """lo9i's data, sealed with the password: a file to import on another computer. 400: a password too short,
        or the data couldn't be read."""
        folder = Path(tempfile.mkdtemp(prefix="lo9i-export-"))
        out = folder / export_name()
        try:
            await service.export_data(out, body.password)
        except (MigrationError, OSError) as e:
            shutil.rmtree(folder, ignore_errors=True)
            raise HTTPException(400, message(e)) from e
        removed = BackgroundTask(shutil.rmtree, folder, ignore_errors=True)
        return FileResponse(out, media_type="application/octet-stream", filename=out.name, background=removed)

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
        texts = await service.texts(request.headers.get(LANGUAGE_HEADER))
        return texts.within(replace(report, waiting_for_runs=waiting))


def export_name() -> str:
    return f"lo9i-export-{date.today().isoformat()}.tar.gz.enc"
