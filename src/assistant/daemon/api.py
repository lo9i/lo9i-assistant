"""The daemon's HTTP API. Commands are plain requests; a run's events stream as Server-Sent Events."""

import json
from functools import partial
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from assistant.core.agent import (
    AssistantService,
    Conversation,
    ConversationError,
    EmailError,
    EmailProvider,
    EmailStatus,
    InvalidNameError,
    InvalidTokenError,
    Job,
    JobError,
    MemorySnapshot,
    Session,
    ShownMessage,
    Skill,
    SkillError,
    SkillSummary,
    TelegramStatus,
    UsageReport,
)
from assistant.core.attachments import Attachment
from assistant.core.config import settings
from assistant.daemon.auth import DeviceStreams, add_device_routes, device_of, is_trusted, require_device
from assistant.daemon.clients import ClientRegistry
from assistant.daemon.launchd import StartupError
from assistant.daemon.runs import RunHub
from assistant.daemon.web_ui import BUILD_DIR, add_web_ui, is_web_ui
from assistant.protocol import CLIENT_HEADER, CLIENT_ID_HEADER, END, ConnectedClient, StartupStatus


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


class Ok(BaseModel):
    ok: bool = True


class ThreadCreated(BaseModel):
    thread_id: str


class RunStarted(BaseModel):
    run_id: str


class CancelResult(BaseModel):
    cancelled: bool


# How the OpenAPI schema describes a route that answers with Server-Sent Events.
_EVENT_STREAM: dict[int | str, dict[str, Any]] = {200: {"content": {"text/event-stream": {}}}}


# Host names a browser may use for the localhost port. Anything else is a page on another site
# whose domain was pointed at 127.0.0.1 (DNS rebinding).
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def create_app(service: AssistantService, hub: RunHub, startup: Any = None, web_ui: Path = BUILD_DIR) -> FastAPI:
    app = FastAPI(title="lo9i daemon")
    # Checked outside in: the host name, the client header, then the device.
    require_device(app, service)
    _require_client_header(app)
    _require_known_host(app)
    _add_security_headers(app)
    clients = ClientRegistry(service.bus, leave=partial(service.leave_thread, settings.owner_id))
    streams = DeviceStreams()
    add_device_routes(app, service, streams)
    _add_client_routes(app, service, clients, streams)
    _add_session_routes(app, service, clients)
    _add_run_routes(app, service, hub, clients, streams)
    _add_conversation_routes(app, service, clients)
    _add_telegram_routes(app, service)
    _add_email_routes(app, service)
    _add_skill_routes(app, service)
    _add_job_routes(app, service)
    _add_identity_routes(app, service)
    _add_usage_routes(app, service)
    if startup is not None:
        _add_startup_routes(app, startup)
    add_web_ui(app, web_ui)
    return app


def _require_client_header(app: FastAPI) -> None:
    """Rejects requests without the client header. A web page can't add a custom header to a
    request to another origin without CORS approval, which the daemon never gives, so a site open
    in your browser can't send commands to 127.0.0.1. Not authentication: that comes later (A7 in BACKLOG.md)."""

    @app.middleware("http")
    async def check(request: Request, call_next):
        exempt = request.url.path == "/health" or is_web_ui(request.url.path)
        if not exempt and not request.headers.get(CLIENT_HEADER):
            return JSONResponse({"detail": f"Missing {CLIENT_HEADER} header"}, status_code=403)
        return await call_next(request)


def _require_known_host(app: FastAPI) -> None:
    """Rejects network requests that name a host other than localhost or HTTPS_HOST. A site that
    points its domain at the daemon's address is same-origin with it, so the client header alone
    wouldn't stop its pages. The Unix socket has no browser behind it."""
    known = _LOCAL_HOSTS | ({settings.https_host} if settings.https_host else set())

    @app.middleware("http")
    async def check(request: Request, call_next):
        if not is_trusted(request) and request.url.hostname not in known:
            return JSONResponse({"detail": "Unknown host"}, status_code=403)
        return await call_next(request)


def _add_security_headers(app: FastAPI) -> None:
    """Browsers that reached the daemon over HTTPS never try plain HTTP for it again, and no other
    site may show the web UI in a frame (its own policy is a <meta> tag, which can't say that)."""

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if is_web_ui(request.url.path):
            response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        return response


def _add_client_routes(
    app: FastAPI, service: AssistantService, clients: ClientRegistry, streams: DeviceStreams
) -> None:
    @app.get("/events", response_class=EventSourceResponse, responses=_EVENT_STREAM)
    async def events(request: Request, after: int | None = None) -> EventSourceResponse:
        """Everything that changes while no run is open: memory, skills, jobs, integrations, runs
        started from other channels. Clients keep this open for their whole session, so it also
        tells which clients are connected. A new connection starts from now; a reconnection sends
        the last id it received and gets what it missed."""
        start = resume_point(service.bus.last_id, request.headers.get("last-event-id"), after)
        events = _bus_events(service, start, clients, _client(request))
        return EventSourceResponse(streams.guard(events, device_of(request)), ping=15)

    @app.get("/clients")
    async def connected_clients() -> list[ConnectedClient]:
        return clients.list()


def _add_session_routes(app: FastAPI, service: AssistantService, clients: ClientRegistry) -> None:
    @app.get("/health")
    async def health() -> Ok:
        return Ok()

    @app.post("/threads")
    async def new_thread(request: Request) -> ThreadCreated:
        """A new conversation for the calling client, which leaves the one it was on."""
        thread_id = await service.new_thread(settings.owner_id)
        clients.on_thread(_client_id(request), thread_id)
        return ThreadCreated(thread_id=thread_id)

    @app.get("/memory")
    async def memory() -> MemorySnapshot:
        return await service.memory_snapshot(settings.owner_id)


def _add_run_routes(
    app: FastAPI, service: AssistantService, hub: RunHub, clients: ClientRegistry, streams: DeviceStreams
) -> None:
    @app.post("/threads/{thread_id}/messages")
    async def send(
        thread_id: str,
        request: Request,
        channel: Annotated[str, Form()],
        text: Annotated[str, Form()] = "",
        files: Annotated[list[UploadFile] | None, File()] = None,
    ) -> RunStarted:
        attachments = [await _attachment(f) for f in files or []]
        session = Session(settings.owner_id, channel, thread_id)
        client_id = _client_id(request)
        clients.on_thread(client_id, thread_id)
        run = hub.start(thread_id, service.send(session, text, attachments), channel, client_id, text)
        return RunStarted(run_id=run.id)

    @app.post("/threads/{thread_id}/approvals")
    async def approve(thread_id: str, body: Approvals, request: Request) -> RunStarted:
        session = Session(settings.owner_id, body.channel, thread_id)
        run = hub.start(thread_id, service.resume(session, body.decisions), body.channel, _client_id(request))
        return RunStarted(run_id=run.id)

    @app.post("/threads/{thread_id}/cancel")
    async def cancel(thread_id: str) -> CancelResult:
        return CancelResult(cancelled=await service.cancel(thread_id))

    @app.get("/runs/{run_id}/events", response_class=EventSourceResponse, responses=_EVENT_STREAM)
    async def run_events(run_id: str, request: Request, after: int = 0) -> EventSourceResponse:
        run = hub.get(run_id)
        if run is None:
            raise HTTPException(404, "Unknown or expired run")
        start = int(request.headers.get("last-event-id") or after)
        return EventSourceResponse(streams.guard(_sse(hub.follow(run, start)), device_of(request)))


def _add_conversation_routes(app: FastAPI, service: AssistantService, clients: ClientRegistry) -> None:
    @app.get("/conversations")
    async def conversation_list() -> list[Conversation]:
        return await service.list_conversations(settings.owner_id)

    @app.get("/conversations/{thread_id}/messages")
    async def conversation_messages(thread_id: str) -> list[ShownMessage]:
        return await service.conversation_messages(thread_id)

    @app.post("/conversations/{thread_id}/resume")
    async def resume_conversation(thread_id: str, request: Request) -> Ok:
        """Moves the calling client to an earlier conversation, leaving the one it was on."""
        try:
            await service.require_conversation(settings.owner_id, thread_id)
        except ConversationError as e:
            raise HTTPException(404, str(e)) from e
        clients.on_thread(_client_id(request), thread_id)
        return Ok()


def _add_telegram_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/integrations/telegram")
    async def telegram_status() -> TelegramStatus:
        return await service.telegram_status()

    @app.post("/integrations/telegram")
    async def connect_telegram(body: TelegramToken) -> TelegramStatus:
        try:
            return await service.connect_telegram(body.token)
        except InvalidTokenError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/integrations/telegram/pairing")
    async def telegram_pairing() -> TelegramStatus:
        return await service.start_telegram_pairing()

    @app.delete("/integrations/telegram")
    async def disconnect_telegram() -> Ok:
        await service.disconnect_telegram()
        return Ok()


def _add_email_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/integrations/email/providers")
    async def email_providers() -> list[EmailProvider]:
        return service.email_providers()

    @app.get("/integrations/email")
    async def email_status() -> EmailStatus:
        return await service.email_status()

    @app.post("/integrations/email")
    async def connect_email(body: EmailSettings) -> EmailStatus:
        try:
            return await service.connect_email(body.host, body.port, body.username, body.password, body.sender)
        except EmailError as e:
            raise HTTPException(400, str(e)) from e

    @app.put("/integrations/email/recipients")
    async def email_recipients(body: EmailRecipients) -> EmailStatus:
        return await service.set_email_recipients(body.addresses)

    @app.delete("/integrations/email")
    async def disconnect_email() -> Ok:
        await service.disconnect_email()
        return Ok()


def _add_skill_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/skills")
    async def skills() -> list[SkillSummary]:
        return await service.list_skills()

    @app.get("/skills/{name}")
    async def skill(name: str) -> Skill:
        try:
            return await service.get_skill(name)
        except SkillError as e:
            raise HTTPException(404, str(e)) from e

    @app.delete("/skills/{name}")
    async def delete_skill(name: str) -> Ok:
        try:
            await service.delete_skill(name)
        except SkillError as e:
            raise HTTPException(404, str(e)) from e
        return Ok()


def _add_job_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/jobs")
    async def jobs() -> list[Job]:
        return await service.list_jobs(settings.owner_id)

    @app.patch("/jobs/{name}")
    async def change_job(name: str, body: JobChange) -> Job:
        try:
            return await service.set_job_enabled(settings.owner_id, name, body.enabled)
        except JobError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/jobs/{name}")
    async def delete_job(name: str) -> Ok:
        try:
            await service.delete_job(settings.owner_id, name)
        except JobError as e:
            raise HTTPException(404, str(e)) from e
        return Ok()


def _add_identity_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/assistant")
    async def assistant() -> AssistantName:
        return AssistantName(name=await service.assistant_name())

    @app.put("/assistant")
    async def rename_assistant(body: AssistantName) -> AssistantName:
        try:
            return AssistantName(name=await service.rename_assistant(body.name))
        except InvalidNameError as e:
            raise HTTPException(400, str(e)) from e


def _add_usage_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/usage")
    async def usage(days: int = 7) -> UsageReport:
        return await service.usage_report(days)


def _add_startup_routes(app: FastAPI, startup: Any) -> None:
    """Start at boot (macOS LaunchDaemon). `startup` offers status(), enable() and disable()."""

    @app.get("/system/startup")
    async def startup_status() -> StartupStatus:
        return startup.status()

    @app.post("/system/startup")
    async def enable_startup() -> StartupStatus:
        try:
            return await startup.enable()
        except StartupError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/system/startup")
    async def disable_startup() -> StartupStatus:
        try:
            return await startup.disable()
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


def resume_point(last_id: int, last_event_id: str | None, after: int | None) -> int:
    """The event id a bus stream starts after: the one the client last received, or the latest."""
    if last_event_id:
        return int(last_event_id)
    return last_id if after is None else after


def _client_id(request: Request) -> str:
    return request.headers.get(CLIENT_ID_HEADER, "")


def _client(request: Request) -> tuple[str, str, str]:
    """(id, kind, transport). Connections on the Unix socket have no peer address."""
    peer = request.client
    transport = f"{peer.host}:{peer.port}" if peer and peer.host else "unix socket"
    return request.headers.get(CLIENT_ID_HEADER, ""), request.headers.get(CLIENT_HEADER, ""), transport
