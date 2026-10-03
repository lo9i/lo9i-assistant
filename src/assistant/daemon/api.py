"""The daemon's HTTP API. Commands are plain requests; a run's events stream as Server-Sent Events."""

import json
from collections.abc import Awaitable
from functools import partial
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from assistant.core.agent import (
    Alert,
    AssistantService,
    Conversation,
    ConversationBusyError,
    ConversationError,
    Decoding,
    EmailAccount,
    EmailAccountNotFoundError,
    EmailError,
    EmailProvider,
    InstalledFromRepository,
    InvalidNameError,
    InvalidSearchKeyError,
    InvalidTokenError,
    Job,
    JobError,
    McpProbe,
    McpServer,
    McpServerChanges,
    McpServerError,
    McpServerStatus,
    MemorySnapshot,
    ModelProvider,
    ModelSettingsError,
    ModelStatus,
    PluginUpdate,
    RepositoryContents,
    RepositoryError,
    ServerValues,
    Session,
    ShownMessage,
    SignedIn,
    SignInError,
    Skill,
    SkillError,
    SkillSummary,
    SlackError,
    SlackStatus,
    SpeechSettingsError,
    SpeechStatus,
    SpokenReplies,
    SynthesisError,
    TelegramStatus,
    TokenReport,
    UsageReport,
    WebSearchStatus,
)
from assistant.core.attachments import Attachment
from assistant.core.config import settings
from assistant.core.health import Area
from assistant.core.memory.profile import MAX_ITEMS, Section
from assistant.core.repositories.known import EXTRAS
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


class BraveKey(BaseModel):
    key: str


class SlackTokens(BaseModel):
    app_token: str
    bot_token: str
    user_token: str


class SlackManifest(BaseModel):
    manifest: str


class EmailSettings(BaseModel):
    # What the user calls the account; the sender address when empty.
    label: str = ""
    host: str
    port: int
    username: str
    # Empty when changing an account keeps its saved password.
    password: str
    sender: str
    # Reading mail; empty for sending only.
    imap_host: str = ""
    imap_port: int = 993


class NewMailAlerts(BaseModel):
    # telegram, slack, or "" for none.
    channel: str


class EmailAccountName(BaseModel):
    label: str


class EmailSignIn(BaseModel):
    # google or microsoft.
    provider: str
    # The user's OAuth app; the secret is typed in the dialog and stays in the daemon.
    client_id: str
    client_secret: str = ""
    # Where the provider sends the browser back: the web app's /app/oauth page.
    redirect_uri: str
    address: str
    label: str = ""
    # Signing an existing account in again.
    account_id: str = ""


class SignInPage(BaseModel):
    url: str


class SignInCode(BaseModel):
    state: str
    code: str


class McpSignInStart(BaseModel):
    # Where the server's authorization server sends the browser back: the web app's /app/oauth page.
    redirect_uri: str


class EmailRecipients(BaseModel):
    addresses: list[str]


class ModelChange(BaseModel):
    provider: str
    # The provider's fields by key (ModelProvider.fields). A secret left empty keeps the saved one
    # when the provider stays the same.
    values: dict[str, str] = {}
    model: str
    worker_model: str


class SpeechChange(BaseModel):
    model: str
    languages: list[str]
    # accurate or fast; left out, it stays as it is.
    decoding: Decoding | None = None


class SpokenRepliesChange(BaseModel):
    spoken_replies: SpokenReplies
    voice: str


class SpeakRequest(BaseModel):
    text: str
    # Empty: the reply voice from the settings.
    voice: str = ""


class SkillChange(BaseModel):
    description: str
    instructions: str


class RepositoryAddress(BaseModel):
    # The apps leave it out: plugins come from the assistant's own extras.
    url: str = EXTRAS


class ProfileItems(BaseModel):
    items: list[str] = Field(max_length=MAX_ITEMS)


class PluginUpdateChecks(BaseModel):
    enabled: bool


class ServerValuesBody(BaseModel):
    name: str
    # Values for the server's fields (env values or headers); secrets, never shown again.
    values: dict[str, str] = {}


class RepositoryInstall(BaseModel):
    url: str = EXTRAS
    skills: list[str] = []
    servers: list[ServerValuesBody] = []


class JobChange(BaseModel):
    enabled: bool


class McpServerSettings(BaseModel):
    name: str
    # Either command (a local server) or url (a remote one).
    command: str = ""
    args: list[str] = []
    env: dict[str, str] = {}
    url: str = ""
    headers: dict[str, str] = {}
    trusted: bool = False
    include: list[str] = []
    exclude: list[str] = []

    def server(self) -> McpServer:
        return McpServer(**self.model_dump())


class McpServerChange(BaseModel):
    """Fields to change; the ones left out keep their value."""

    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    enabled: bool | None = None
    trusted: bool | None = None
    include: list[str] | None = None
    exclude: list[str] | None = None


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


# How the OpenAPI schema describes a route that answers with audio.
_WAV: dict[int | str, dict[str, Any]] = {200: {"content": {"audio/wav": {}}}}

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
    _add_slack_routes(app, service)
    _add_web_search_routes(app, service)
    _add_email_routes(app, service)
    _add_sign_in_routes(app, service)
    _add_skill_routes(app, service)
    _add_job_routes(app, service)
    _add_mcp_routes(app, service)
    _add_alert_routes(app, service)
    _add_repository_routes(app, service)
    _add_identity_routes(app, service)
    _add_speech_routes(app, service)
    _add_model_routes(app, service)
    _add_usage_routes(app, service)
    if startup is not None:
        _add_startup_routes(app, startup)
    add_web_ui(app, web_ui)
    return app


def _require_client_header(app: FastAPI) -> None:
    """Rejects requests without the client header. A web page can't add a custom header to a
    request to another origin without CORS approval, which the daemon never gives, so a site open
    in your browser can't send commands to 127.0.0.1. Not authentication, which is daemon/auth.py."""

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

    @app.put("/memory/profile/{section}")
    async def set_profile_section(section: Section, body: ProfileItems) -> MemorySnapshot:
        """Replaces one profile section with the user's own list. 422: an unknown section or too many items."""
        return await service.set_profile_section(settings.owner_id, section, body.items)


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

    @app.delete("/conversations/{thread_id}")
    async def delete_conversation(thread_id: str, request: Request) -> Ok:
        """Deletes a conversation no client is on. 404: no such conversation; 409: a client is on
        it or a reply is running."""
        _refuse_if_open(clients, thread_id, _client_id(request))
        try:
            await service.delete_conversation(settings.owner_id, thread_id)
        except ConversationBusyError as e:
            raise HTTPException(409, str(e)) from e
        except ConversationError as e:
            raise HTTPException(404, str(e)) from e
        return Ok()


def _refuse_if_open(clients: ClientRegistry, thread_id: str, caller: str) -> None:
    on_it = clients.on(thread_id)
    if caller in on_it:
        raise HTTPException(409, "You're on this conversation. Start a new one first, then delete it.")
    if on_it:
        raise HTTPException(409, "It's open in another window or app. Move that one to another conversation first.")


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


def _add_web_search_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/integrations/web-search")
    async def web_search_status() -> WebSearchStatus:
        return await service.web_search_status()

    @app.put("/integrations/web-search/brave-key")
    async def set_brave_key(body: BraveKey) -> WebSearchStatus:
        try:
            return await service.set_brave_key(body.key)
        except InvalidSearchKeyError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/integrations/web-search/brave-key")
    async def remove_brave_key() -> WebSearchStatus:
        return await service.remove_brave_key()


def _add_slack_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/integrations/slack")
    async def slack_status() -> SlackStatus:
        return await service.slack_status()

    @app.get("/integrations/slack/manifest")
    async def slack_manifest() -> SlackManifest:
        return SlackManifest(manifest=await service.slack_manifest())

    @app.post("/integrations/slack")
    async def connect_slack(body: SlackTokens) -> SlackStatus:
        try:
            return await service.connect_slack(body.app_token, body.bot_token, body.user_token)
        except SlackError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/integrations/slack")
    async def disconnect_slack() -> Ok:
        await service.disconnect_slack()
        return Ok()


def _add_model_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/settings/model/providers")
    async def model_providers() -> list[ModelProvider]:
        return service.model_providers()

    @app.get("/settings/model")
    async def model_status() -> ModelStatus:
        return await service.model_status()

    @app.put("/settings/model")
    async def set_model(body: ModelChange) -> ModelStatus:
        """Checks that both models answer with these settings, then uses them."""
        try:
            return await service.set_model(body.provider, body.values, body.model, body.worker_model)
        except ModelSettingsError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/settings/model")
    async def reset_model() -> ModelStatus:
        """Back to the model in .env."""
        return await service.reset_model()


def _add_speech_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/settings/speech")
    async def speech_settings() -> SpeechStatus:
        return await service.speech_settings()

    @app.put("/settings/speech")
    async def set_speech(body: SpeechChange) -> SpeechStatus:
        try:
            return await service.set_speech(body.model, body.languages, body.decoding)
        except SpeechSettingsError as e:
            raise HTTPException(400, str(e)) from e

    @app.put("/settings/speech/replies")
    async def set_spoken_replies(body: SpokenRepliesChange) -> SpeechStatus:
        try:
            return await service.set_spoken_replies(body.spoken_replies, body.voice)
        except SpeechSettingsError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/speech", response_class=Response, responses=_WAV)
    async def speak(body: SpeakRequest) -> Response:
        """The text read aloud on this host (Kokoro), as WAV."""
        try:
            return Response(await service.speak(body.text, "wav", body.voice), media_type="audio/wav")
        except SynthesisError as e:
            raise HTTPException(400, str(e)) from e


def _add_email_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/integrations/email/providers")
    async def email_providers() -> list[EmailProvider]:
        return service.email_providers()

    @app.get("/integrations/email/accounts")
    async def email_accounts() -> list[EmailAccount]:
        """The default account first."""
        return await service.email_accounts()

    @app.post("/integrations/email/accounts")
    async def add_email_account(body: EmailSettings) -> EmailAccount:
        """Checks the logins with the servers first. The first account becomes the default."""
        return await _email(
            service.add_email_account(
                body.label,
                body.host,
                body.port,
                body.username,
                body.password,
                body.sender,
                body.imap_host,
                body.imap_port,
            )
        )

    @app.put("/integrations/email/accounts/{account_id}")
    async def update_email_account(account_id: str, body: EmailSettings) -> EmailAccount:
        return await _email(
            service.update_email_account(
                account_id,
                body.label,
                body.host,
                body.port,
                body.username,
                body.password,
                body.sender,
                body.imap_host,
                body.imap_port,
            )
        )

    @app.post("/integrations/email/oauth/start")
    async def start_email_sign_in(body: EmailSignIn) -> SignInPage:
        """The provider's sign-in page; the browser comes back to `redirect_uri`. 400: unknown
        provider or missing values. 404: unknown account."""
        page = await _email(
            service.start_email_sign_in(
                body.provider,
                body.client_id,
                body.client_secret,
                body.redirect_uri,
                body.address,
                body.label,
                body.account_id,
            )
        )
        return SignInPage(url=page)

    @app.put("/integrations/email/accounts/{account_id}/label")
    async def rename_email_account(account_id: str, body: EmailAccountName) -> EmailAccount:
        """Only the name; the sign-in stays."""
        return await _email(service.rename_email_account(account_id, body.label))

    @app.put("/integrations/email/accounts/{account_id}/default")
    async def default_email_account(account_id: str) -> EmailAccount:
        return await _email(service.set_default_email_account(account_id))

    @app.put("/integrations/email/accounts/{account_id}/alerts")
    async def new_mail_alerts(account_id: str, body: NewMailAlerts) -> EmailAccount:
        return await _email(service.set_new_mail_alerts(account_id, body.channel))

    @app.put("/integrations/email/accounts/{account_id}/recipients")
    async def email_recipients(account_id: str, body: EmailRecipients) -> EmailAccount:
        return await _email(service.set_email_recipients(account_id, body.addresses))

    @app.delete("/integrations/email/accounts/{account_id}")
    async def remove_email_account(account_id: str) -> Ok:
        await _email(service.remove_email_account(account_id))
        return Ok()


async def _email[T](call: Awaitable[T]) -> T:
    """404 for an unknown account, 400 for anything else that went wrong."""
    try:
        return await call
    except EmailAccountNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except EmailError as e:
        raise HTTPException(400, str(e)) from e


def _add_sign_in_routes(app: FastAPI, service: AssistantService) -> None:
    @app.post("/oauth/finish")
    async def finish_sign_in(body: SignInCode) -> SignedIn:
        """The last step of a sign-in (an email account, a remote MCP server). Open to unpaired
        browsers: the one-time state is the proof (the web app's /app/oauth page may be opened on
        the daemon's own computer, before pairing). 400: expired state, refused code, or a server
        that won't work with the tokens."""
        try:
            return await service.finish_sign_in(body.state, body.code)
        except (SignInError, EmailError, McpServerError) as e:
            raise HTTPException(400, str(e)) from e


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

    @app.put("/skills/{name}")
    async def update_skill(name: str, body: SkillChange) -> Skill:
        """404: no such skill. 400: built in, or the text is empty."""
        try:
            await service.get_skill(name)
        except SkillError as e:
            raise HTTPException(404, str(e)) from e
        try:
            return await service.update_skill(name, body.description, body.instructions)
        except SkillError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/skills/{name}/update")
    async def update_installed_skill(name: str) -> Skill:
        """Install the skill again from its repository. 404: no such skill. 400: not installed, or
        the repository can't be read."""
        try:
            await service.get_skill(name)
        except SkillError as e:
            raise HTTPException(404, str(e)) from e
        try:
            return await service.update_installed_skill(name)
        except (SkillError, RepositoryError) as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/skills/{name}")
    async def delete_skill(name: str) -> Ok:
        """404: no such skill. 400: built in, or it comes with an MCP server."""
        try:
            await service.get_skill(name)
        except SkillError as e:
            raise HTTPException(404, str(e)) from e
        try:
            await service.delete_skill(name)
        except SkillError as e:
            raise HTTPException(400, str(e)) from e
        return Ok()


def _add_repository_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/repositories/updates")
    async def plugin_updates() -> list[PluginUpdate]:
        """Installed plugins the extras have a newer version of, as of the last check. Empty while
        checks are off."""
        return await service.plugin_updates()

    @app.get("/settings/plugin-updates")
    async def plugin_update_checks() -> PluginUpdateChecks:
        return PluginUpdateChecks(enabled=await service.plugin_update_checks())

    @app.put("/settings/plugin-updates")
    async def set_plugin_update_checks(body: PluginUpdateChecks) -> PluginUpdateChecks:
        return PluginUpdateChecks(enabled=await service.set_plugin_update_checks(body.enabled))

    @app.post("/repositories/browse")
    async def browse_repository(body: RepositoryAddress) -> RepositoryContents:
        """The skills and MCP servers a git repository offers. 400: it can't be read or has none."""
        try:
            return await service.browse_repository(body.url)
        except RepositoryError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/repositories/install")
    async def install_from_repository(body: RepositoryInstall) -> InstalledFromRepository:
        """400: the repository can't be read, lacks something picked, a name is taken, or a field is empty."""
        wanted = [ServerValues(s.name, s.values) for s in body.servers]
        try:
            return await service.install_from_repository(body.url, body.skills, wanted)
        except (RepositoryError, SkillError, McpServerError) as e:
            raise HTTPException(400, str(e)) from e


def _add_mcp_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/mcp/servers")
    async def mcp_servers() -> list[McpServerStatus]:
        return await service.mcp_servers()

    @app.post("/mcp/probe")
    async def probe_mcp_server(body: McpServerSettings) -> McpProbe:
        """Connect once and list the server's tools, without saving it. A remote server may ask to
        sign in instead: it can be added, then signed in to."""
        try:
            return await service.probe_mcp_server(body.server())
        except McpServerError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/mcp/servers")
    async def add_mcp_server(body: McpServerSettings) -> McpServerStatus:
        try:
            return await service.add_mcp_server(body.server())
        except McpServerError as e:
            raise HTTPException(400, str(e)) from e

    @app.patch("/mcp/servers/{name}")
    async def change_mcp_server(name: str, body: McpServerChange) -> McpServerStatus:
        try:
            return await service.update_mcp_server(name, McpServerChanges(**body.model_dump()))
        except McpServerError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/mcp/servers/{name}/sign-in")
    async def start_mcp_sign_in(name: str, body: McpSignInStart) -> SignInPage:
        """The server's sign-in page; the browser comes back to `redirect_uri`, which finishes it
        (/oauth/finish). 404: no such server. 400: a local server, one that can't be reached or
        doesn't ask to sign in."""
        if name not in {s.name for s in await service.mcp_servers()}:
            raise HTTPException(404, f"No MCP server named {name}.")
        try:
            return SignInPage(url=await service.start_mcp_sign_in(name, body.redirect_uri))
        except McpServerError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/mcp/servers/{name}/update")
    async def update_mcp_server_from_repository(name: str) -> McpServerStatus:
        """Install the server again from its repository. 404: no such server. 400: not installed
        from one, the repository can't be read, or the new version needs a value not given yet."""
        if name not in {s.name for s in await service.mcp_servers()}:
            raise HTTPException(404, f"No MCP server named {name}.")
        try:
            return await service.update_mcp_server_from_repository(name)
        except (McpServerError, RepositoryError) as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/mcp/servers/{name}")
    async def remove_mcp_server(name: str, delete_data: bool = False) -> Ok:
        """With `delete_data`, the server's data folder goes too; otherwise it stays."""
        try:
            await service.remove_mcp_server(name, delete_data)
        except McpServerError as e:
            raise HTTPException(404, str(e)) from e
        return Ok()


def _add_alert_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/alerts")
    async def alerts() -> list[Alert]:
        """MCP servers and skills that keep failing, the newest first."""
        return await service.alerts()

    @app.post("/alerts/{area}/{name}/dismiss")
    async def dismiss_alert(area: Area, name: str) -> Ok:
        await service.dismiss_alert(area, name)
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

    @app.get("/usage/tokens")
    async def token_usage(days: int = 7) -> TokenReport:
        """Tokens and cost of the model calls, by day, model, purpose, channel, conversation, job, skill and tool."""
        return await service.token_report(days)


def _add_startup_routes(app: FastAPI, startup: Any) -> None:
    """Start at boot (daemon/startup.py). `startup` offers status(), enable() and disable()."""

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


async def _bus_events(
    service: AssistantService, after: int, clients: ClientRegistry, client: tuple[str, str, str, str]
):
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


def _client(request: Request) -> tuple[str, str, str, str]:
    """(id, kind, transport, device id). Connections on the Unix socket have no peer address and no device."""
    peer = request.client
    transport = f"{peer.host}:{peer.port}" if peer and peer.host else "unix socket"
    device = device_of(request)
    client_id, kind = request.headers.get(CLIENT_ID_HEADER, ""), request.headers.get(CLIENT_HEADER, "")
    return client_id, kind, transport, device.id if device else ""
