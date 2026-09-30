"""The daemon's HTTP API. Commands are plain requests; a run's events stream as Server-Sent Events."""

import json
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from assistant.core.agent import AssistantService, InvalidToken, Session
from assistant.core.attachments import Attachment
from assistant.core.config import settings
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER, END


class Approvals(BaseModel):
    channel: str
    decisions: dict[str, dict[str, Any]]


class TelegramToken(BaseModel):
    token: str


def create_app(service: AssistantService, hub: RunHub) -> FastAPI:
    app = FastAPI(title="lo9i daemon")
    _require_client_header(app)
    _add_session_routes(app, service)
    _add_run_routes(app, service, hub)
    _add_telegram_routes(app, service)
    return app


def _require_client_header(app: FastAPI) -> None:
    """Rejects requests without the client header. A web page can't add a custom header to a
    request to another origin without CORS approval, which the daemon never gives, so a site open
    in your browser can't send commands to 127.0.0.1. Not authentication: that comes later (A6)."""

    @app.middleware("http")
    async def check(request: Request, call_next):
        if request.url.path != "/health" and not request.headers.get(CLIENT_HEADER):
            return JSONResponse({"detail": f"Missing {CLIENT_HEADER} header"}, status_code=403)
        return await call_next(request)


def _add_session_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/sessions/{channel}")
    async def session(channel: str) -> dict[str, str]:
        return asdict(await service.session(settings.owner_id, channel))

    @app.post("/threads")
    async def new_thread() -> dict[str, str]:
        return {"thread_id": await service.new_thread(settings.owner_id)}

    @app.get("/memory")
    async def memory() -> dict[str, Any]:
        return asdict(await service.memory_snapshot(settings.owner_id))


def _add_run_routes(app: FastAPI, service: AssistantService, hub: RunHub) -> None:
    @app.post("/threads/{thread_id}/messages")
    async def send(
        thread_id: str, channel: str = Form(...), text: str = Form(""), files: list[UploadFile] = File(default=[])
    ) -> dict[str, str]:
        attachments = [await _attachment(f) for f in files]
        session = Session(settings.owner_id, channel, thread_id)
        return {"run_id": hub.start(thread_id, service.send(session, text, attachments)).id}

    @app.post("/threads/{thread_id}/approvals")
    async def approve(thread_id: str, body: Approvals) -> dict[str, str]:
        session = Session(settings.owner_id, body.channel, thread_id)
        return {"run_id": hub.start(thread_id, service.resume(session, body.decisions)).id}

    @app.get("/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request, after: int = 0) -> EventSourceResponse:
        run = hub.get(run_id)
        if run is None:
            raise HTTPException(404, "Unknown or expired run")
        start = int(request.headers.get("last-event-id") or after)
        return EventSourceResponse(_sse(hub.follow(run, start)))


def _add_telegram_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/integrations/telegram")
    async def telegram_status() -> dict[str, Any]:
        return asdict(await service.telegram_status())

    @app.post("/integrations/telegram")
    async def connect_telegram(body: TelegramToken) -> dict[str, Any]:
        try:
            return asdict(await service.connect_telegram(body.token))
        except InvalidToken as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/integrations/telegram/pairing")
    async def telegram_pairing() -> dict[str, Any]:
        return asdict(await service.start_telegram_pairing())

    @app.delete("/integrations/telegram")
    async def disconnect_telegram() -> dict[str, bool]:
        await service.disconnect_telegram()
        return {"ok": True}


async def _attachment(upload: UploadFile) -> Attachment:
    data = await upload.read()
    return Attachment(name=upload.filename or "file", media_type=upload.content_type or "application/octet-stream", data=data)


async def _sse(events):
    async for event_id, event in events:
        if event is None:
            yield {"id": str(event_id), "event": END, "data": "{}"}
        else:
            yield {"id": str(event_id), "data": json.dumps(event)}
