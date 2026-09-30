"""The daemon's HTTP API. Commands are plain requests; a run's events stream as Server-Sent Events."""

import json
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from assistant.core.agent import (
    AssistantService,
    EmailError,
    InvalidNameError,
    InvalidTokenError,
    JobError,
    Session,
    SkillError,
)
from assistant.core.attachments import Attachment
from assistant.core.config import settings
from assistant.daemon.clients import ClientRegistry
from assistant.daemon.launchd import StartupError
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER, CLIENT_ID_HEADER, END


class Approvals(BaseModel):
    channel: str
    decisions: dict[str, dict[str, Any]]


class TelegramToken(BaseModel):
    token: str


class EmailSettings(BaseModel):
    host: str
    port: int
    username: str
    password: str
    sender: str


class EmailRecipients(BaseModel):
    addresses: list[str]


class JobChange(BaseModel):
    enabled: bool


class AssistantName(BaseModel):
    name: str


def create_app(service: AssistantService, hub: RunHub, startup: Any = None) -> FastAPI:
    app = FastAPI(title="lo9i daemon")
    _require_client_header(app)
    _add_client_routes(app, service, ClientRegistry(service.bus))
    _add_session_routes(app, service)
    _add_run_routes(app, service, hub)
    _add_telegram_routes(app, service)
    _add_email_routes(app, service)
    _add_skill_routes(app, service)
    _add_job_routes(app, service)
    _add_identity_routes(app, service)
    _add_usage_routes(app, service)
    if startup is not None:
        _add_startup_routes(app, startup)
    return app


def _require_client_header(app: FastAPI) -> None:
    """Rejects requests without the client header. A web page can't add a custom header to a
    request to another origin without CORS approval, which the daemon never gives, so a site open
    in your browser can't send commands to 127.0.0.1. Not authentication: that comes later (A7 in BACKLOG.md)."""

    @app.middleware("http")
    async def check(request: Request, call_next):
        if request.url.path != "/health" and not request.headers.get(CLIENT_HEADER):
            return JSONResponse({"detail": f"Missing {CLIENT_HEADER} header"}, status_code=403)
        return await call_next(request)


def _add_client_routes(app: FastAPI, service: AssistantService, clients: ClientRegistry) -> None:
    @app.get("/events")
    async def events(request: Request, after: int = 0) -> EventSourceResponse:
        """Everything that changes while no run is open: memory, skills, jobs, integrations, runs
        started from other channels. Clients keep this open for their whole session, so it also
        tells which clients are connected."""
        start = int(request.headers.get("last-event-id") or after)
        return EventSourceResponse(_bus_events(service, start, clients, _client(request)), ping=15)

    @app.get("/clients")
    async def connected_clients() -> list[dict[str, str]]:
        return [asdict(c) for c in clients.list()]


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
        thread_id: str,
        channel: Annotated[str, Form()],
        text: Annotated[str, Form()] = "",
        files: Annotated[list[UploadFile] | None, File()] = None,
    ) -> dict[str, str]:
        attachments = [await _attachment(f) for f in files or []]
        session = Session(settings.owner_id, channel, thread_id)
        run = hub.start(thread_id, service.send(session, text, attachments), channel=channel, text=text)
        return {"run_id": run.id}

    @app.post("/threads/{thread_id}/approvals")
    async def approve(thread_id: str, body: Approvals) -> dict[str, str]:
        session = Session(settings.owner_id, body.channel, thread_id)
        return {"run_id": hub.start(thread_id, service.resume(session, body.decisions), channel=body.channel).id}

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
        except InvalidTokenError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/integrations/telegram/pairing")
    async def telegram_pairing() -> dict[str, Any]:
        return asdict(await service.start_telegram_pairing())

    @app.delete("/integrations/telegram")
    async def disconnect_telegram() -> dict[str, bool]:
        await service.disconnect_telegram()
        return {"ok": True}


def _add_email_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/integrations/email")
    async def email_status() -> dict[str, Any]:
        return asdict(await service.email_status())

    @app.post("/integrations/email")
    async def connect_email(body: EmailSettings) -> dict[str, Any]:
        try:
            return asdict(await service.connect_email(body.host, body.port, body.username, body.password, body.sender))
        except EmailError as e:
            raise HTTPException(400, str(e)) from e

    @app.put("/integrations/email/recipients")
    async def email_recipients(body: EmailRecipients) -> dict[str, Any]:
        return asdict(await service.set_email_recipients(body.addresses))

    @app.delete("/integrations/email")
    async def disconnect_email() -> dict[str, bool]:
        await service.disconnect_email()
        return {"ok": True}


def _add_skill_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/skills")
    async def skills() -> list[dict[str, str]]:
        return [asdict(s) for s in await service.list_skills()]

    @app.get("/skills/{name}")
    async def skill(name: str) -> dict[str, str]:
        try:
            return asdict(await service.get_skill(name))
        except SkillError as e:
            raise HTTPException(404, str(e)) from e

    @app.delete("/skills/{name}")
    async def delete_skill(name: str) -> dict[str, bool]:
        try:
            await service.delete_skill(name)
        except SkillError as e:
            raise HTTPException(404, str(e)) from e
        return {"ok": True}


def _add_job_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/jobs")
    async def jobs() -> list[dict[str, Any]]:
        return [asdict(j) for j in await service.list_jobs(settings.owner_id)]

    @app.patch("/jobs/{name}")
    async def change_job(name: str, body: JobChange) -> dict[str, Any]:
        try:
            return asdict(await service.set_job_enabled(settings.owner_id, name, body.enabled))
        except JobError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/jobs/{name}")
    async def delete_job(name: str) -> dict[str, bool]:
        try:
            await service.delete_job(settings.owner_id, name)
        except JobError as e:
            raise HTTPException(404, str(e)) from e
        return {"ok": True}


def _add_identity_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/assistant")
    async def assistant() -> dict[str, str]:
        return {"name": await service.assistant_name()}

    @app.put("/assistant")
    async def rename_assistant(body: AssistantName) -> dict[str, str]:
        try:
            return {"name": await service.rename_assistant(body.name)}
        except InvalidNameError as e:
            raise HTTPException(400, str(e)) from e


def _add_usage_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/usage")
    async def usage(days: int = 7) -> dict[str, Any]:
        return asdict(await service.usage_report(days))


def _add_startup_routes(app: FastAPI, startup: Any) -> None:
    """Start at boot (macOS LaunchDaemon). `startup` offers status(), enable() and disable()."""

    @app.get("/system/startup")
    async def startup_status() -> dict[str, Any]:
        return asdict(startup.status())

    @app.post("/system/startup")
    async def enable_startup() -> dict[str, Any]:
        try:
            return asdict(await startup.enable())
        except StartupError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/system/startup")
    async def disable_startup() -> dict[str, Any]:
        try:
            return asdict(await startup.disable())
        except StartupError as e:
            raise HTTPException(400, str(e)) from e


async def _attachment(upload: UploadFile) -> Attachment:
    data = await upload.read()
    return Attachment(
        name=upload.filename or "file", media_type=upload.content_type or "application/octet-stream", data=data
    )


async def _sse(events):
    async for event_id, event in events:
        if event is None:
            yield {"id": str(event_id), "event": END, "data": "{}"}
        else:
            yield {"id": str(event_id), "data": json.dumps(event)}


async def _bus_events(service: AssistantService, after: int, clients: ClientRegistry, client: tuple[str, str, str]):
    """The client is listed as connected for as long as it reads the stream."""
    key = clients.add(*client)
    try:
        async for event in service.bus.subscribe(after):
            yield {"id": str(event.id), "event": event.kind, "data": json.dumps(event.data)}
    finally:
        clients.remove(key)


def _client(request: Request) -> tuple[str, str, str]:
    """(id, kind, transport). Connections on the Unix socket have no peer address."""
    peer = request.client
    transport = f"{peer.host}:{peer.port}" if peer and peer.host else "unix socket"
    return request.headers.get(CLIENT_ID_HEADER, ""), request.headers.get(CLIENT_HEADER, ""), transport
