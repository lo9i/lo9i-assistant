"""The daemon's HTTP API. Commands are plain requests; a run's events stream as Server-Sent Events."""

import contextlib
import json
from collections.abc import AsyncGenerator, Awaitable, Mapping
from dataclasses import asdict, replace
from functools import partial
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from assistant.core.agent import (
    Agent,
    AgentFolders,
    Alert,
    AlertArea,
    AssistantService,
    ChannelNotConnectedError,
    ChannelStatus,
    Conversation,
    ConversationBusyError,
    ConversationError,
    ConversationStats,
    Decoding,
    DoctorPage,
    EmailAccount,
    EmailAccountNotFoundError,
    EmailError,
    EmailProvider,
    Episode,
    Fact,
    FilePreview,
    FileUnavailableError,
    FolderChanges,
    FolderContents,
    FolderError,
    FolderListing,
    HandedFolderError,
    Handoff,
    HandoffError,
    HomePage,
    HomeSection,
    HomeSectionsError,
    Importables,
    ImportOutcome,
    InstalledFromRepository,
    InvalidNameError,
    InvalidSearchKeyError,
    Job,
    JobError,
    KeptKeys,
    Language,
    LanguageError,
    McpProbe,
    McpServer,
    McpServerChanges,
    McpServerError,
    McpServerStatus,
    MemoryEditError,
    MemoryNotFoundError,
    MemorySnapshot,
    MissingPathError,
    ModelOption,
    ModelProvider,
    ModelSettingsError,
    ModelStatus,
    NotHandedError,
    Notification,
    PluginUpdate,
    PromptEditError,
    PromptSection,
    Repository,
    RepositoryContents,
    RepositoryError,
    RepositoryPlugins,
    RunningTask,
    ServerValues,
    Session,
    SetupItem,
    ShownCall,
    ShownMessage,
    SignedIn,
    SignInError,
    Skill,
    SkillError,
    SkillSummary,
    SpeechSettingsError,
    SpeechStatus,
    SpokenReplies,
    SynthesisError,
    TokenReport,
    UnknownPromptError,
    UploadedFile,
    UsageReport,
    WebSearchStatus,
)
from assistant.core.attachments import Attachment
from assistant.core.channels.chat.conversations import ChannelChats
from assistant.core.channels.chat.port import ChatLimits
from assistant.core.config import settings
from assistant.core.conversation.dispatch_setting import DispatchSetting, DispatchSettingError
from assistant.core.events import ApprovalRequired
from assistant.core.logs import (
    MAX_LINES,
    LogEntry,
    LogLevel,
    LogLevelError,
    LogOptions,
    LogPage,
    LogQuery,
    LogQueryError,
    LogSource,
    log_options,
)
from assistant.core.memory.profile import MAX_ITEMS, Section
from assistant.core.repositories.known import EXTRAS
from assistant.daemon import host
from assistant.daemon.auth import (
    DeviceStreams,
    add_device_routes,
    channel_of,
    device_of,
    is_trusted,
    require_device,
)
from assistant.daemon.channel_runs import ChannelRuns
from assistant.daemon.clients import ClientRegistry
from assistant.daemon.launchd import StartupError
from assistant.daemon.run_follows import RunFollows, StreamKey
from assistant.daemon.runs import Run, RunHub
from assistant.daemon.shutdown import Ending
from assistant.daemon.web_ui import BUILD_DIR, add_web_ui, is_web_ui
from assistant.protocol import (
    CLIENT_HEADER,
    CLIENT_ID_HEADER,
    END,
    ConnectedClient,
    HostStatus,
    NoEndingError,
    PendingEnding,
    ShutdownStatus,
    StartupStatus,
    StopRefusedError,
    UpdateError,
    UpdateStatus,
)


class Approvals(BaseModel):
    channel: str
    decisions: dict[str, dict[str, Any]]


class BraveKey(BaseModel):
    key: str


class ChannelItems(BaseModel):
    items: list[SetupItem]


class DeliveryResult(BaseModel):
    # Empty when the channel carried out the operation; otherwise why it couldn't.
    error: str = ""
    # The id of the message it sent, for a `send`.
    message: str = ""


class ChannelPress(BaseModel):
    """A button pressed in a chat: the button's data, on `message` whose text is `text`."""

    chat: str
    message: str
    text: str = ""
    data: str


class ChannelCommand(BaseModel):
    # Without its slash: new, start, or an agent's (claude).
    command: str
    # What follows it: an agent's folder, or off.
    text: str = ""


class CommandReply(BaseModel):
    text: str


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
    # The email plugin whose provider it's connected with; "" for servers entered by hand. Only
    # read when adding an account: an account stays with its plugin.
    plugin: str = ""


class NewMailAlerts(BaseModel):
    # An installed chat channel, or "" for none.
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
    # The email plugin a new account belongs to.
    plugin: str = ""


class SignInPage(BaseModel):
    url: str


class SignInCode(BaseModel):
    state: str
    code: str


class McpSignInStart(BaseModel):
    # Where the server's authorization server sends the browser back: the web app's /app/oauth page.
    redirect_uri: str


class PluginSignInStart(BaseModel):
    # The user's OAuth app; the secret is typed in the dialog and stays in the daemon. An empty client ID signs
    # in again with the app the plugin signed in with.
    client_id: str = ""
    client_secret: str = ""
    # Where the provider sends the browser back: the web app's /app/oauth page.
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


class ModelValues(BaseModel):
    provider: str
    # The provider's fields by key; a secret left empty uses the saved one for the same provider.
    values: dict[str, str] = {}


class SpeechChange(BaseModel):
    model: str
    languages: list[str]
    # accurate or fast; left out, it stays as it is.
    decoding: Decoding | None = None


class SpokenRepliesChange(BaseModel):
    spoken_replies: SpokenReplies
    voice: str


class FollowRun(BaseModel):
    run_id: str
    # How many of the run's events the client has: its events after them are sent.
    after: int = 0


class SpeakRequest(BaseModel):
    text: str
    # Empty: the reply voice from the settings.
    voice: str = ""


class LogLevelSetting(BaseModel):
    # The lowest level the daemon records.
    level: LogLevel


class LogLevelChange(BaseModel):
    # Checked by the service, which says what the choices are.
    level: str


class LanguageSetting(BaseModel):
    # auto follows each browser's language in the web app, and is English elsewhere.
    language: Language


class LanguageChange(BaseModel):
    # Checked by the service, which says what the choices are.
    language: str


class PromptText(BaseModel):
    text: str


class HomeRefresh(BaseModel):
    # Even when the last refresh is fresh (the Refresh button).
    force: bool = False


class HomeSections(BaseModel):
    sections: list[HomeSection]


class SkillChange(BaseModel):
    description: str
    instructions: str


class SkillImport(BaseModel):
    # Importable.id of each skill the user picked.
    ids: list[str]
    # A skill with the same name is replaced instead of the import getting another name.
    replace: bool = False


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


class Removed(BaseModel):
    # What the removed plugin left kept (its keys, its private repository's token), for the apps to
    # ask whether to keep it; None when nothing is.
    kept: KeptKeys | None = None


class RepositoryUrl(BaseModel):
    url: str


class RepositoryAdd(BaseModel):
    url: str
    # For a private repository: a token that can read it, kept encrypted and never shown again.
    token: str = ""


class RepositoryInstall(BaseModel):
    url: str = EXTRAS
    skills: list[str] = []
    servers: list[ServerValuesBody] = []


class JobChange(BaseModel):
    enabled: bool


class CancelledRuns(BaseModel):
    cancelled: int


class JobRunReply(BaseModel):
    """A job run's whole reply; its record keeps only the end of it."""

    text: str


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


class MemoryText(BaseModel):
    text: str


class ConversationAgent(BaseModel):
    # The agent the conversation is handed to; None while the assistant answers.
    handoff: Handoff | None = None


class HandTo(BaseModel):
    # The agent's command, without the slash: "claude".
    command: str
    folder: str


class PinnedSkills(BaseModel):
    # In the order they were pinned.
    skills: list[str]


class RunStarted(BaseModel):
    run_id: str


class Dispatching(BaseModel):
    channel: str
    # What the message said, announced with the run so other clients show it, and for a coding task the assistant
    # moved out of the inbox, the agent it's for (the Dispatched event's `brief`).
    text: str = ""
    brief: str = ""


class Moving(BaseModel):
    channel: str
    # The message to move, from the inbox's record of it; empty for the last one the inbox sent on.
    id: str = ""


class Routing(BaseModel):
    # The first message of a new conversation, as the user wrote it.
    text: str


class Routed(BaseModel):
    # The conversation it continues; empty for the new one.
    thread_id: str


class ConversationsContaining(BaseModel):
    thread_ids: list[str]


class RunInProgress(BaseModel):
    run_id: str
    thread_id: str
    channel: str
    # As announced in its `run` event: the client that started it, what the user wrote, the notice of a follow-up,
    # and for a coding task the assistant wrote instead, the agent it's for.
    client_id: str = ""
    text: str = ""
    notice: str = ""
    brief: str = ""

    @classmethod
    def of(cls, run: Run) -> "RunInProgress":
        return cls(
            run_id=run.id,
            thread_id=run.thread_id,
            channel=run.channel,
            client_id=run.client_id,
            text=run.text,
            notice=run.notice,
            brief=run.brief,
        )


class ShownConversation(BaseModel):
    """A conversation as a client opens it while its runs may be in progress."""

    # Its messages up to the first run in progress, which `runs` shows from its start.
    messages: list[ShownMessage]
    runs: list[RunInProgress]


class CancelResult(BaseModel):
    cancelled: bool


# How the OpenAPI schema describes a route that answers with audio.
_WAV: dict[int | str, dict[str, Any]] = {200: {"content": {"audio/wav": {}}}}

# How the OpenAPI schema describes a route that answers with a file.
_FILE: dict[int | str, dict[str, Any]] = {200: {"content": {"application/octet-stream": {}}}}

# How the OpenAPI schema describes a route that answers with Server-Sent Events.
_EVENT_STREAM: dict[int | str, dict[str, Any]] = {200: {"content": {"text/event-stream": {}}}}


# Host names a browser may use for the localhost port. Anything else is a page on another site
# whose domain was pointed at 127.0.0.1 (DNS rebinding).
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def create_app(
    service: AssistantService,
    hub: RunHub,
    startup: Any = None,
    shutdown: Any = None,
    web_ui: Path = BUILD_DIR,
    logs: Mapping[str, LogSource] | None = None,
    streams: DeviceStreams | None = None,
    updates: Any = None,
) -> FastAPI:
    """`streams` is shared with the pages app, so revoking a device also closes its pages' WebSockets."""
    app = FastAPI(title="lo9i daemon")
    # Checked outside in: the host name, the client header, then the device.
    require_device(app, service)
    _require_client_header(app)
    _require_known_host(app)
    _add_security_headers(app)
    clients = ClientRegistry(
        service.bus, leave=partial(service.leave_thread, settings.owner_id), gone=service.unwatch_home
    )
    streams = streams or DeviceStreams()
    follows = RunFollows(hub)
    add_device_routes(app, service, streams)
    _add_client_routes(app, service, clients, streams, follows)
    _add_session_routes(app, service, clients)
    _add_run_routes(app, service, hub, clients, streams)
    _add_run_follow_routes(app, hub, follows)
    _add_conversation_routes(app, service, clients)
    _add_pinned_skill_routes(app, service)
    _add_memory_routes(app, service)
    _add_handoff_routes(app, service)
    _add_handed_folder_routes(app, service)
    _add_file_routes(app, service)
    _add_channel_routes(app, service)
    _add_channel_plugin_routes(app, service)
    _add_channel_chat_routes(app, service, hub)
    _add_web_search_routes(app, service)
    _add_email_routes(app, service)
    _add_sign_in_routes(app, service)
    _add_skill_routes(app, service)
    _add_skill_import_routes(app, service)
    _add_job_routes(app, service)
    _add_mcp_routes(app, service)
    _add_alert_routes(app, service)
    _add_doctor_routes(app, service)
    _add_notification_routes(app, service)
    _add_home_routes(app, service)
    _add_task_routes(app, service)
    _add_repository_routes(app, service)
    _add_identity_routes(app, service)
    _add_prompt_routes(app, service)
    _add_speech_routes(app, service)
    _add_log_level_routes(app, service)
    _add_dispatch_routes(app, service)
    _add_language_routes(app, service)
    _add_model_routes(app, service)
    _add_usage_routes(app, service)
    _add_host_route(app, shutdown)
    if startup is not None:
        _add_startup_routes(app, startup)
    if shutdown is not None:
        _add_shutdown_routes(app, shutdown)
    if updates is not None:
        _add_update_routes(app, updates)
    if logs is not None:
        _add_log_routes(app, logs, streams)
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
    app: FastAPI, service: AssistantService, clients: ClientRegistry, streams: DeviceStreams, follows: RunFollows
) -> None:
    @app.get("/events", response_class=EventSourceResponse, responses=_EVENT_STREAM)
    async def events(request: Request, after: int | None = None) -> EventSourceResponse:
        """Everything that changes while no run is open: memory, skills, jobs, integrations, runs
        started from other channels. Clients keep this open for their whole session, so it also
        tells which clients are connected. A new connection starts from now; a reconnection sends
        the last id it received and gets what it missed. The runs the client follows
        (`PUT /events/runs/<id>`) come down it too."""
        start = resume_point(service.bus.last_id, request.headers.get("last-event-id"), after)
        events = follows.events(_stream_key(request), _bus_events(service, start, clients, _client(request)))
        return EventSourceResponse(streams.guard(events, device_of(request)), ping=15)

    @app.get("/clients")
    async def connected_clients() -> list[ConnectedClient]:
        return clients.list()


def _add_run_follow_routes(app: FastAPI, hub: RunHub, follows: RunFollows) -> None:
    @app.put("/events/runs/{follow_id}")
    async def follow_run(follow_id: str, body: FollowRun, request: Request) -> Ok:
        """Sends a run's events after `after` down this client's /events stream (`run_events`, then `run_end`), so a
        browser follows every run on the one connection (daemon/run_follows.py). Asked again under the same id, as
        after the stream reconnected, it starts again from `after`."""
        if not _client_id(request):
            raise HTTPException(400, "Only a client that names itself (X-Lo9i-Client-Id) has a stream to follow on")
        run = hub.get(body.run_id)
        if run is None:
            raise HTTPException(404, "Unknown or expired run")
        follows.follow(_stream_key(request), follow_id, run, body.after)
        return Ok()

    @app.delete("/events/runs/{follow_id}")
    async def unfollow_run(follow_id: str, request: Request) -> Ok:
        follows.stop(_stream_key(request), follow_id)
        return Ok()


def _add_session_routes(app: FastAPI, service: AssistantService, clients: ClientRegistry) -> None:
    @app.get("/health")
    async def health() -> Ok:
        return Ok()

    @app.post("/threads/inbox")
    async def inbox_thread(request: Request) -> ThreadCreated:
        """Moves the calling client to the inbox, which routes each message to its conversation, leaving the
        one it was on."""
        thread_id = await service.inbox_thread(settings.owner_id)
        clients.on_thread(_client_id(request), thread_id)
        return ThreadCreated(thread_id=thread_id)

    @app.post("/threads")
    async def new_thread(request: Request) -> ThreadCreated:
        """A new conversation for the calling client, which leaves the one it was on."""
        thread_id = await service.new_thread(settings.owner_id)
        clients.on_thread(_client_id(request), thread_id)
        return ThreadCreated(thread_id=thread_id)

    @app.post("/threads/leave")
    async def leave_thread(request: Request) -> Ok:
        """The calling client closes its conversation without moving to another, as a closed chat tab."""
        clients.off_thread(_client_id(request))
        return Ok()

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

    @app.post("/threads/{thread_id}/dispatched/{dispatch_id}")
    async def send_dispatched(thread_id: str, dispatch_id: str, request: Request, body: Dispatching) -> RunStarted:
        """Sends a message the inbox sent on (a Dispatched event) here, as it was written."""
        session = Session(settings.owner_id, body.channel, thread_id)
        client_id = _client_id(request)
        clients.on_thread(client_id, thread_id)
        events = service.send_dispatched(session, dispatch_id)
        run = hub.start(thread_id, events, body.channel, client_id, body.text, brief=body.brief)
        return RunStarted(run_id=run.id)

    @app.post("/threads/{thread_id}/moves")
    async def move_dispatched(thread_id: str, request: Request, body: Moving) -> RunStarted:
        """Asks in the inbox where a message it sent on goes instead, and sends it on again (a Dispatched
        event)."""
        session = Session(settings.owner_id, body.channel, thread_id)
        events = service.move_dispatched(session, body.id or None)
        run = hub.start(thread_id, events, body.channel, _client_id(request))
        return RunStarted(run_id=run.id)

    @app.post("/routes")
    async def route_first_message(body: Routing) -> Routed:
        """Where the first message of a conversation opened for no topic goes: on in the conversation it's about,
        or in the new one. Nothing is sent; the client sends it there."""
        return Routed(thread_id=await service.route_first_message(settings.owner_id, body.text))

    @app.post("/threads/{thread_id}/approvals")
    async def approve(thread_id: str, body: Approvals, request: Request) -> RunStarted:
        session = Session(settings.owner_id, body.channel, thread_id)
        run = hub.start(thread_id, service.resume(session, body.decisions), body.channel, _client_id(request))
        return RunStarted(run_id=run.id)

    @app.post("/threads/{thread_id}/cancel")
    async def cancel(thread_id: str) -> CancelResult:
        return CancelResult(cancelled=await service.cancel(thread_id))

    @app.get("/runs")
    async def runs_in_progress() -> list[RunInProgress]:
        """Replies in progress in any conversation, oldest first. `run` and `run_finished` events tell
        when this changes."""
        return [RunInProgress.of(r) for r in hub.running()]

    @app.get("/conversations/{thread_id}/live")
    async def live_conversation(thread_id: str) -> ShownConversation:
        """Its messages up to its runs in progress, and those runs, oldest first, which a client follows from
        their start (`/runs/<id>/events`) to show them as if it had been watching."""
        # Listed before the messages are read, with no wait between: a run listed here that ends while they're read
        # still stops them where it started.
        runs = [RunInProgress.of(r) for r in hub.running(thread_id)]
        return ShownConversation(messages=await service.messages_before_run(thread_id), runs=runs)

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

    # Before /conversations/{thread_id}, which would take "containing" as an id.
    @app.get("/conversations/containing")
    async def conversations_containing(q: str) -> ConversationsContaining:
        """The ids of the conversations whose messages hold every word of `q`, each as the start of a word, in no
        order: what a search box adds to the titles it matches."""
        return ConversationsContaining(thread_ids=await service.conversations_containing(settings.owner_id, q))

    @app.get("/conversations/{thread_id}")
    async def conversation(thread_id: str) -> Conversation:
        """One conversation as the list shows it: its title, tags and channels. 404: it isn't listed (a new one
        before its first message); `conversations` events tell when it changes."""
        try:
            return await service.conversation(settings.owner_id, thread_id)
        except ConversationError as e:
            raise HTTPException(404, str(e)) from e

    @app.get("/conversations/{thread_id}/messages")
    async def conversation_messages(thread_id: str) -> list[ShownMessage]:
        return await service.conversation_messages(thread_id)

    @app.get("/conversations/{thread_id}/tool-calls/{call_id}")
    async def conversation_tool_call(thread_id: str, call_id: str) -> ShownCall:
        """A tool call in full: its messages show each call's arguments on one line and the start of its output,
        `partial` when that leaves something out. 404: the conversation has no such call."""
        try:
            return await service.conversation_tool_call(thread_id, call_id)
        except ConversationError as e:
            raise HTTPException(404, str(e)) from e

    @app.get("/conversations/{thread_id}/tool-calls/{call_id}/steps/{index}")
    async def conversation_tool_call_step(thread_id: str, call_id: str, index: int) -> ShownCall:
        """A step inside a tool call in full (a delegate call's subagent's, a task's, a handed-off agent's own
        subagent's), by its place from 0: the call shows each step's start, `partial` when that leaves something
        out. 404: the call has no such step."""
        try:
            return await service.conversation_tool_call_step(thread_id, call_id, index)
        except ConversationError as e:
            raise HTTPException(404, str(e)) from e

    @app.get("/conversations/{thread_id}/stats")
    async def conversation_stats(thread_id: str) -> ConversationStats:
        """Its messages, tokens and tool calls, and when it started and was last written in. All zero for a
        new one; `run_finished` events tell when they may have changed."""
        return await service.conversation_stats(settings.owner_id, thread_id)

    @app.get("/conversations/{thread_id}/approvals")
    async def pending_approvals(thread_id: str) -> list[ApprovalRequired]:
        """What its run stopped to ask and still waits for, whoever started it, so a client opening it
        can ask the user. Answered with POST /threads/<id>/approvals; empty when nothing waits."""
        return await service.pending_approvals(thread_id)

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


def _add_handoff_routes(app: FastAPI, service: AssistantService) -> None:
    """Conversations handed to a plugin's agent (core/conversation/handoffs.py)."""

    @app.get("/agents")
    async def agents() -> list[Agent]:
        """The agents installed plugins bring, with the command the apps offer for each."""
        return await service.agents()

    @app.get("/agents/folders")
    async def agent_folders() -> AgentFolders:
        """The folders the apps offer to hand a conversation to: the workspace and the ones used before."""
        return await service.agent_folders(settings.owner_id)

    @app.get("/agents/folders/children")
    async def child_folders(path: str, hidden: bool = False) -> FolderListing:
        """The folders inside `path`, to browse to one; hidden ones (named with a dot) too when `hidden`. 400: not
        a full path, or it can't be read."""
        try:
            return await service.child_folders(path, hidden)
        except FolderError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/conversations/{thread_id}/agent")
    async def conversation_agent(thread_id: str) -> ConversationAgent:
        return ConversationAgent(handoff=await service.conversation_agent(settings.owner_id, thread_id))

    @app.put("/conversations/{thread_id}/agent")
    async def hand_conversation(thread_id: str, body: HandTo) -> ConversationAgent:
        """400: no plugin brings that agent, or the folder doesn't exist."""
        try:
            handoff = await service.hand_conversation(settings.owner_id, thread_id, body.command, body.folder)
        except HandoffError as e:
            raise HTTPException(400, str(e)) from e
        return ConversationAgent(handoff=handoff)

    @app.delete("/conversations/{thread_id}/agent")
    async def take_back_conversation(thread_id: str) -> ConversationAgent:
        await service.take_back_conversation(settings.owner_id, thread_id)
        return ConversationAgent()

    @app.post("/conversations/{thread_id}/agent/messages")
    async def message_agent(
        thread_id: str,
        text: Annotated[str, Form()] = "",
        files: Annotated[list[UploadFile] | None, File()] = None,
    ) -> Ok:
        """Passes a message, and the files sent with it, on to the agent while it works on the conversation's
        last one; it takes it between its steps. 400: neither text nor files. 409: it isn't working, or can't
        take messages while it works."""
        if not text.strip() and not files:
            raise HTTPException(400, "Write a message or attach a file.")
        attachments = [await _attachment(f) for f in files or []]
        try:
            await service.message_agent(settings.owner_id, thread_id, text, attachments)
        except HandoffError as e:
            raise HTTPException(409, str(e)) from e
        return Ok()

    @app.post("/conversations/{thread_id}/agent/interrupt")
    async def interrupt_agent(thread_id: str) -> Ok:
        """Stops the agent's step in progress; it waits for the next message. 409 as for messages."""
        try:
            await service.interrupt_agent(settings.owner_id, thread_id)
        except HandoffError as e:
            raise HTTPException(409, str(e)) from e
        return Ok()


def _add_memory_routes(app: FastAPI, service: AssistantService) -> None:
    """Saved facts and summaries of past conversations, edited and deleted from the apps. 404: it's gone;
    400: empty text."""

    @app.get("/memory/facts")
    async def saved_facts() -> list[Fact]:
        return await service.saved_facts(settings.owner_id)

    @app.put("/memory/facts/{fact_id}")
    async def edit_fact(fact_id: str, body: MemoryText) -> Fact:
        return await _memory_call(service.edit_fact(settings.owner_id, fact_id, body.text))

    @app.delete("/memory/facts/{fact_id}")
    async def delete_fact(fact_id: str) -> Ok:
        await _memory_call(service.delete_fact(settings.owner_id, fact_id))
        return Ok()

    @app.get("/memory/episodes")
    async def saved_episodes() -> list[Episode]:
        return await service.saved_episodes(settings.owner_id)

    @app.put("/memory/episodes/{episode_id}")
    async def edit_episode(episode_id: str, body: MemoryText) -> Episode:
        return await _memory_call(service.edit_episode(settings.owner_id, episode_id, body.text))

    @app.delete("/memory/episodes/{episode_id}")
    async def delete_episode(episode_id: str) -> Ok:
        await _memory_call(service.delete_episode(settings.owner_id, episode_id))
        return Ok()


async def _memory_call[T](call: Awaitable[T]) -> T:
    try:
        return await call
    except MemoryNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except MemoryEditError as e:
        raise HTTPException(400, str(e)) from e


def _add_pinned_skill_routes(app: FastAPI, service: AssistantService) -> None:
    """Skills pinned to a conversation: in full in its system prompt from the next user message on."""

    @app.get("/conversations/{thread_id}/pinned")
    async def pinned_skills(thread_id: str) -> PinnedSkills:
        return PinnedSkills(skills=await service.pinned_skills(settings.owner_id, thread_id))

    @app.put("/conversations/{thread_id}/pinned/{name}")
    async def pin_skill(thread_id: str, name: str) -> PinnedSkills:
        """404: no such skill."""
        try:
            return PinnedSkills(skills=await service.pin_skill(settings.owner_id, thread_id, name))
        except SkillError as e:
            raise HTTPException(404, str(e)) from e

    @app.delete("/conversations/{thread_id}/pinned/{name}")
    async def unpin_skill(thread_id: str, name: str) -> PinnedSkills:
        return PinnedSkills(skills=await service.unpin_skill(settings.owner_id, thread_id, name))


def _refuse_if_open(clients: ClientRegistry, thread_id: str, caller: str) -> None:
    on_it = clients.on(thread_id)
    if caller in on_it:
        raise HTTPException(409, "You're on this conversation. Start a new one first, then delete it.")
    if on_it:
        raise HTTPException(409, "It's open in another window or app. Move that one to another conversation first.")


# A page of a list the apps load as it's scrolled (Files, Notifications). Without one, the whole list, as
# the terminal app reads it.
_PageLimit = Annotated[int | None, Query(ge=1, le=200)]
_Offset = Annotated[int, Query(ge=0)]


def _add_handed_folder_routes(app: FastAPI, service: AssistantService) -> None:
    """The folder a conversation is handed to, for the web app's side panel (core/handed_folder/). Paths are relative
    to it. 400: a path outside it, or one the panel doesn't show (.git, node_modules, .venv, what git ignores). 404:
    the conversation isn't with an agent, or the path isn't there."""

    @app.get("/conversations/{thread_id}/agent/folder")
    async def handed_folder_contents(thread_id: str, path: str = "") -> FolderContents:
        """The files and folders in `path`, "" for the folder itself: folders first, then files, by name."""
        return await _handed_folder(service.handed_folder_contents(settings.owner_id, thread_id, path))

    @app.get("/conversations/{thread_id}/agent/folder/file")
    async def handed_folder_file(thread_id: str, path: str) -> FilePreview:
        """A file's text to preview, its start for a big one; none for a file that isn't text."""
        return await _handed_folder(service.handed_folder_file(settings.owner_id, thread_id, path))

    @app.get("/conversations/{thread_id}/agent/folder/changes")
    async def handed_folder_changes(thread_id: str) -> FolderChanges:
        """What git says changed in the folder; nothing outside a repository."""
        return await _handed_folder(service.handed_folder_changes(settings.owner_id, thread_id))


async def _handed_folder[T](reading: Awaitable[T]) -> T:
    try:
        return await reading
    except (NotHandedError, MissingPathError) as e:
        raise HTTPException(404, str(e)) from e
    except HandedFolderError as e:
        raise HTTPException(400, str(e)) from e


def _add_file_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/files")
    async def file_list(q: str = "", offset: _Offset = 0, limit: _PageLimit = None) -> list[UploadedFile]:
        """The files in the user's conversations, sent by them or brought by tool results, newest first: those
        matching `q` (name, type, where it came from or conversation), from `offset`, at most `limit` (all
        without it)."""
        return await service.files_page(settings.owner_id, q, offset, limit)

    @app.get("/files/content", response_class=Response, responses=_FILE)
    async def file_content(path: str) -> Response:
        """One of those files, by its path in the list, to view or save. 404: no such file."""
        try:
            file, data = await service.file_content(settings.owner_id, path)
        except FileUnavailableError as e:
            raise HTTPException(404, str(e)) from e
        disposition = f"inline; filename*=UTF-8''{quote(file.name)}"
        return Response(data, media_type=file.media_type, headers={"Content-Disposition": disposition})


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


def _add_channel_routes(app: FastAPI, service: AssistantService) -> None:
    """For the apps: the installed chat channels and their setup buttons."""

    @app.get("/channels")
    async def channels() -> list[ChannelStatus]:
        return await service.channels()

    @app.post("/channels/{name}/actions/{action}")
    async def press_channel_action(name: str, action: str, request: Request) -> Ok:
        """409: the channel isn't connected."""
        if channel_of(request) is not None:
            raise HTTPException(403, "Only the apps press a channel's buttons.")
        try:
            service.press_channel_action(name, action)
        except ChannelNotConnectedError as e:
            raise HTTPException(409, str(e)) from e
        return Ok()


def _add_channel_plugin_routes(app: FastAPI, service: AssistantService) -> None:
    """For a channel plugin's process, with its token (docs/channel-plugins.md)."""

    @app.get("/channels/{name}/stream", response_class=EventSourceResponse, responses=_EVENT_STREAM)
    async def channel_stream(
        name: str,
        request: Request,
        edit_seconds: float = 1.0,
        draft_limit: int = 3500,
        message_limit: int = 3500,
        voice: bool = False,
    ) -> EventSourceResponse:
        """The channel's limits come with the request: how often it may edit a message, how long a
        draft and a message may be, and whether it sends voice notes."""
        _require_channel(request, name)
        limits = ChatLimits(edit_seconds, draft_limit, message_limit, voice)
        events = service.channels_hub.attach(name, limits)
        return EventSourceResponse(({"event": e.kind, "data": json.dumps(e.data)} async for e in events), ping=15)

    @app.put("/channels/{name}/status")
    async def channel_status(name: str, body: ChannelItems, request: Request) -> Ok:
        _require_channel(request, name)
        service.channels_hub.set_status(name, body.items)
        return Ok()

    @app.post("/channels/{name}/deliveries/{delivery_id}")
    async def channel_delivered(name: str, delivery_id: str, body: DeliveryResult, request: Request) -> Ok:
        _require_channel(request, name)
        service.channels_hub.confirm(delivery_id, body.error, body.message)
        return Ok()


def _add_channel_chat_routes(app: FastAPI, service: AssistantService, hub: RunHub) -> None:
    """What the user does in a channel's chat (core/channels/chat/conversations.py). Each answers at once;
    what follows reaches the chat as operations on the channel's stream."""
    chats = ChannelChats(service, ChannelRuns(hub), service.channels_hub, service.approvals)

    @app.post("/channels/{name}/messages")
    async def channel_message(
        name: str,
        request: Request,
        chat: Annotated[str, Form()],
        text: Annotated[str, Form()] = "",
        voice: Annotated[bool, Form()] = False,
        files: Annotated[list[UploadFile] | None, File()] = None,
        reply_to: Annotated[str, Form()] = "",
        message: Annotated[str, Form()] = "",
    ) -> Ok:
        """`voice`: the message was a voice note (Settings → Audio can speak only those replies). `reply_to`:
        the id of the message it replies to, whose conversation it goes on in; `message`: its own id."""
        _require_channel(request, name)
        attachments = [await _attachment(f) for f in files or []]
        chats.spawn(chats.message(name, chat, text, attachments, voice, reply_to, message))
        return Ok()

    @app.post("/channels/{name}/presses")
    async def channel_press(name: str, body: ChannelPress, request: Request) -> Ok:
        _require_channel(request, name)
        chats.spawn(chats.press(name, body.chat, body.message, body.text, body.data))
        return Ok()

    @app.post("/channels/{name}/commands")
    async def channel_command(name: str, body: ChannelCommand, request: Request) -> CommandReply:
        _require_channel(request, name)
        return CommandReply(text=await chats.command(name, body.command, body.text))


def _require_channel(request: Request, name: str) -> None:
    """These routes are only for the channel's own process."""
    if channel_of(request) != name:
        raise HTTPException(403, f"Only the {name} channel's process uses this.")


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

    @app.post("/settings/model/available")
    async def available_models(body: ModelValues) -> list[ModelOption]:
        """The models the provider offers for these values, to pick from; empty when it can't list
        them. 400: the provider refused the values or can't be reached."""
        try:
            return await service.available_models(body.provider, body.values)
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
        """The presets of the email plugins that are on."""
        return await service.email_providers()

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
                body.plugin,
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
                body.plugin,
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

    @app.get("/integrations/email/recipients")
    async def email_recipients() -> EmailRecipients:
        """Who the agent may email without asking, from any account, besides the user's own accounts."""
        return EmailRecipients(addresses=await service.email_recipients())

    @app.put("/integrations/email/recipients")
    async def set_email_recipients(body: EmailRecipients) -> EmailRecipients:
        return EmailRecipients(addresses=await service.set_email_recipients(body.addresses))

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
        """The last step of a sign-in (an email account, a remote MCP server, a plugin). Open to unpaired
        browsers: the one-time state is the proof (the web app's /app/oauth page may be opened on
        the daemon's own computer, before pairing). 400: expired state, refused code, or a server
        that won't work with the tokens."""
        try:
            return await service.finish_sign_in(body.state, body.code)
        except (SignInError, EmailError, McpServerError) as e:
            raise HTTPException(400, str(e)) from e


def _add_skill_import_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/skill-imports")
    async def importable_skills() -> Importables:
        """Claude Code's and Codex's skills on this computer, each with whether it was imported or changed since."""
        return await service.importable_skills(settings.owner_id)

    @app.post("/skill-imports")
    async def import_skills(body: SkillImport) -> list[ImportOutcome]:
        """Import the skills the user picked; one imported before is updated. Each says how it went."""
        return await service.import_skills(settings.owner_id, body.ids, body.replace)


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
    async def delete_skill(name: str) -> Removed:
        """404: no such skill. 400: built in, or it comes with an MCP server."""
        try:
            await service.get_skill(name)
        except SkillError as e:
            raise HTTPException(404, str(e)) from e
        try:
            return Removed(kept=await service.delete_skill(name))
        except SkillError as e:
            raise HTTPException(400, str(e)) from e


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

    @app.get("/repositories")
    async def repositories() -> list[Repository]:
        """The repositories plugins are listed from: the official extras first, then the added ones."""
        return await service.repositories()

    @app.post("/repositories")
    async def add_repository(body: RepositoryAdd) -> Repository:
        """400: listed already, can't be read (with the token, for a private one), or offers no plugins."""
        try:
            return await service.add_repository(body.url, body.token)
        except RepositoryError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/repositories/remove")
    async def remove_repository(body: RepositoryUrl) -> Ok:
        """Its installed plugins stay. 400: the extras, or a repository not listed."""
        try:
            await service.remove_repository(body.url)
        except RepositoryError as e:
            raise HTTPException(400, str(e)) from e
        return Ok()

    @app.get("/plugins/keys")
    async def kept_plugin_keys() -> list[KeptKeys]:
        """Everything removed plugins left kept: each plugin's keys while it isn't installed again (`repository`
        empty), and each private repository's token nothing needs any more (`plugin` empty). `plugins` and
        `settings` events tell when it may have changed."""
        return await service.kept_keys()

    @app.post("/plugins/keys/forget")
    async def forget_plugin_keys(body: KeptKeys) -> Ok:
        """Delete what a removed plugin left kept (Removed.kept), when the user says so."""
        await service.forget_keys(body)
        return Ok()

    @app.get("/repositories/plugins")
    async def repository_plugins(cached: bool = False) -> list[RepositoryPlugins]:
        """What every listed repository offers; one that can't be read has an error instead.
        `cached=true` answers from the listings kept from the last read, reaching only a repository
        never read; a read that finds something new publishes `plugins`."""
        return await service.repository_plugins(cached)

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

    @app.post("/plugins/{name}/sign-in")
    async def start_plugin_sign_in(name: str, body: PluginSignInStart) -> SignInPage:
        """The provider's sign-in page for a plugin that signs in with the user's own OAuth app (`oauth:` in its
        server.yaml); the browser comes back to `redirect_uri`, which finishes it (/oauth/finish). 404: no such
        plugin. 400: it doesn't sign in, or no client ID."""
        if name not in {s.name for s in await service.mcp_servers()}:
            raise HTTPException(404, f"No plugin named {name}.")
        try:
            return SignInPage(
                url=await service.start_plugin_sign_in(name, body.client_id, body.client_secret, body.redirect_uri)
            )
        except McpServerError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/plugins/{name}/sign-in")
    async def sign_out_plugin(name: str) -> McpServerStatus:
        """Forget the plugin's sign-in. 404: no such plugin."""
        try:
            return await service.sign_out_plugin(name)
        except McpServerError as e:
            raise HTTPException(404, str(e)) from e

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
    async def remove_mcp_server(name: str, delete_data: bool = False) -> Removed:
        """With `delete_data`, the server's data folder goes too; otherwise it stays. Its keys stay
        until the user deletes them (`kept`, POST /plugins/keys/forget)."""
        try:
            return Removed(kept=await service.remove_mcp_server(name, delete_data))
        except McpServerError as e:
            raise HTTPException(404, str(e)) from e


def _add_alert_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/alerts")
    async def alerts() -> list[Alert]:
        """MCP servers and skills that keep failing, and the health check's new or growing causes, the newest
        first."""
        return await service.alerts()

    @app.post("/alerts/{area}/{name}/dismiss")
    async def dismiss_alert(area: AlertArea, name: str) -> Ok:
        await service.dismiss_alert(area, name)
        return Ok()


def _add_doctor_routes(app: FastAPI, service: AssistantService) -> None:
    """The doctor (core/doctor/): the latest health check, checking today now, and the causes marked as known
    noise. Each change publishes `doctor`."""

    @app.get("/doctor")
    async def doctor() -> DoctorPage:
        return await service.doctor_page(settings.owner_id)

    @app.post("/doctor/check")
    async def check_health() -> DoctorPage:
        """Checks today so far in the background, unless a check runs; its report comes with a `doctor` event."""
        return await service.check_health(settings.owner_id)

    @app.put("/doctor/known/{cause_id}")
    async def mark_known(cause_id: str) -> DoctorPage:
        """The cause is noise: left out from now on. 404: the latest check didn't find it."""
        if not await service.mark_known(settings.owner_id, cause_id):
            raise HTTPException(404, f"The latest check found no cause {cause_id}.")
        return await service.doctor_page(settings.owner_id)

    @app.delete("/doctor/known/{cause_id}")
    async def forget_known(cause_id: str) -> DoctorPage:
        """The cause shows again from the next check. 404: it wasn't marked."""
        if not await service.forget_known(settings.owner_id, cause_id):
            raise HTTPException(404, f"No known cause {cause_id}.")
        return await service.doctor_page(settings.owner_id)


def _add_notification_routes(app: FastAPI, service: AssistantService) -> None:
    """The notifications feed (core/notifications.py): job results and background work that ended."""

    @app.get("/notifications")
    async def notification_list(offset: _Offset = 0, limit: _PageLimit = None) -> list[Notification]:
        """The newest first, from `offset`, at most `limit` (all without it)."""
        return await service.notifications(settings.owner_id, offset, limit)

    @app.post("/notifications/read")
    async def read_notifications() -> Ok:
        await service.mark_notifications_read(settings.owner_id)
        return Ok()

    @app.delete("/notifications/{notification_id}")
    async def dismiss_notification(notification_id: str) -> Ok:
        """404: no such notification."""
        if not await service.dismiss_notification(settings.owner_id, notification_id):
            raise HTTPException(404, f"No notification {notification_id}.")
        return Ok()

    @app.delete("/notifications")
    async def clear_notifications() -> Ok:
        await service.clear_notifications(settings.owner_id)
        return Ok()


def _add_home_routes(app: FastAPI, service: AssistantService) -> None:
    """Home (core/home/): its sections with their last results; each result saved publishes `home`."""

    @app.get("/home")
    async def home() -> HomePage:
        return await service.home(settings.owner_id)

    @app.post("/home/refresh")
    async def refresh_home(body: HomeRefresh) -> HomePage:
        """Builds the sections again in the background, unless a refresh runs or, unforced, the last one is
        under ten minutes old."""
        return await service.refresh_home(settings.owner_id, body.force)

    @app.put("/home/watch")
    async def watch_home(request: Request) -> Ok:
        """The calling client shows Home: it's refreshed every half hour while it does, until DELETE or until the
        client disconnects."""
        service.watch_home(_client_id(request))
        return Ok()

    @app.delete("/home/watch")
    async def unwatch_home(request: Request) -> Ok:
        service.unwatch_home(_client_id(request))
        return Ok()

    @app.put("/home/sections")
    async def save_home_sections(body: HomeSections) -> HomePage:
        """The new and changed ones are built in the background. 400: sections that can't be saved."""
        try:
            return await service.save_home_sections(settings.owner_id, body.sections)
        except HomeSectionsError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/home/sections")
    async def reset_home_sections() -> HomePage:
        """Back to the built-in sections."""
        return await service.reset_home_sections(settings.owner_id)


def _add_task_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/agent-tasks/running")
    async def running_tasks() -> list[RunningTask]:
        """Coding agents' tasks still running, the newest first, with their latest steps."""
        return await service.running_tasks()


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

    @app.get("/jobs/{name}/reply")
    async def job_run_reply(name: str, at: str) -> JobRunReply:
        """The reply of the job's run that started `at`, as the notification of that run links to it."""
        try:
            return JobRunReply(text=await service.job_run_reply(settings.owner_id, name, at))
        except JobError as e:
            raise HTTPException(404, str(e)) from e

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


def _add_prompt_routes(app: FastAPI, service: AssistantService) -> None:
    """The system prompt texts the user edits (core/conversation/prompt_edits.py), used from the next
    user message in each conversation."""

    @app.get("/settings/prompts")
    async def prompt_sections() -> list[PromptSection]:
        return await service.prompt_sections()

    @app.put("/settings/prompts/{name}")
    async def save_prompt(name: str, body: PromptText) -> PromptSection:
        """404: not a prompt the user can edit. 400: an empty text, or the edit can't be written."""
        try:
            return await service.save_prompt(name, body.text)
        except UnknownPromptError as e:
            raise HTTPException(404, str(e)) from e
        except PromptEditError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/settings/prompts/{name}/kept")
    async def keep_prompt(name: str) -> PromptSection:
        """Keeps the edit as it is after the built-in text changed (`built_in_changes`), which isn't said again.
        404: not a prompt the user can edit. 400: that can't be recorded."""
        try:
            return await service.keep_prompt(name)
        except UnknownPromptError as e:
            raise HTTPException(404, str(e)) from e
        except PromptEditError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/settings/prompts/{name}")
    async def reset_prompt(name: str) -> PromptSection:
        """Back to the built-in text. 404: not a prompt the user can edit. 400: the edit can't be deleted."""
        try:
            return await service.reset_prompt(name)
        except UnknownPromptError as e:
            raise HTTPException(404, str(e)) from e
        except PromptEditError as e:
            raise HTTPException(400, str(e)) from e


def _add_usage_routes(app: FastAPI, service: AssistantService) -> None:
    @app.get("/usage")
    async def usage(days: int = 7) -> UsageReport:
        return await service.usage_report(days)

    @app.get("/usage/tokens")
    async def token_usage(days: int = 7) -> TokenReport:
        """Tokens and cost of the model calls, by day, model, purpose, channel, conversation, job, skill and tool."""
        return await service.token_report(days)


def _add_host_route(app: FastAPI, shutdown: Any | None) -> None:
    @app.get("/system/host")
    async def host_status() -> HostStatus:
        """The computer the daemon runs on: system, versions, CPU, memory, disk, uptime and load, and why the
        daemon can't be stopped from the apps now, if it can't."""
        refusal = shutdown.stop_refusal() if shutdown is not None else None
        return replace(await host.status(), stop_refusal=refusal or "")


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

    @app.post("/system/startup/reinstall")
    async def reinstall_startup() -> StartupStatus:
        """Installs start at boot again, bringing an out-of-date one up to date (`outdated`). A daemon it started
        restarts once no run is in progress, which can't be taken back. 400: it's off, or the password was refused."""
        try:
            return await startup.reinstall()
        except StartupError as e:
            raise HTTPException(400, str(e)) from e


def _add_shutdown_routes(app: FastAPI, shutdown: Any) -> None:
    """Restarting or stopping the daemon once no run is in progress (daemon/shutdown.py). `shutdown` offers
    request(ending), pending(), take_back() and now(). The answer goes out before the daemon stops: stopping waits
    for requests in progress."""

    @app.post("/system/restart")
    async def restart_daemon(request: Request) -> ShutdownStatus:
        return ShutdownStatus(waiting_for_runs=shutdown.request(Ending.RESTART, _asker(request)))

    @app.post("/system/stop")
    async def stop_daemon(request: Request) -> ShutdownStatus:
        try:
            return ShutdownStatus(waiting_for_runs=shutdown.request(Ending.STOP, _asker(request)))
        except StopRefusedError as e:
            raise HTTPException(409, str(e)) from e

    @app.get("/system/ending")
    async def pending_ending() -> PendingEnding:
        """The restart or stop waiting for runs to end; `ending` is "" when none is."""
        return _pending(shutdown)

    @app.delete("/system/ending")
    async def take_back_ending(request: Request) -> PendingEnding:
        """The daemon keeps running. 409: nothing is waiting, it already went ahead, or something needs it (an
        update installed, start at boot installed again: `can_take_back` is false), so it can't be taken back."""
        try:
            shutdown.take_back(_asker(request))
        except NoEndingError as e:
            raise HTTPException(409, str(e)) from e
        return _pending(shutdown)

    @app.post("/system/ending/now")
    async def end_now(request: Request) -> CancelledRuns:
        """Cancels the runs the restart or stop waits for, so it goes ahead. 409: nothing is waiting."""
        try:
            return CancelledRuns(cancelled=shutdown.now(_asker(request)))
        except NoEndingError as e:
            raise HTTPException(409, str(e)) from e


def _pending(shutdown: Any) -> PendingEnding:
    pending = shutdown.pending()
    if pending is None:
        return PendingEnding("", 0)
    return PendingEnding(
        pending.ending.value,
        pending.waiting_for_runs,
        pending.waiting_for_update,
        pending.can_take_back,
        pending.needed_by,
    )


def _asker(request: Request) -> str:
    """Who asked, for the log: the kind of client, and the paired device or the Unix socket."""
    device = device_of(request)
    kind = request.headers.get(CLIENT_HEADER, "") or "a client"
    return f"{kind} ({f'device {device.name}' if device else 'unix socket'})"


def _add_update_routes(app: FastAPI, updates: Any) -> None:
    """The version the daemon runs and installing a newer one (daemon/updates.py). `updates` offers status(),
    check() and start(). An `update` event tells the apps each change of its state."""

    @app.get("/system/update")
    async def update_status() -> UpdateStatus:
        """As of the last check; doesn't reach the repository."""
        return await updates.status()

    @app.post("/system/update/check")
    async def check_for_update() -> UpdateStatus:
        """Fetches the repository and says what's new."""
        return await updates.check()

    @app.post("/system/update")
    async def install_update() -> UpdateStatus:
        """Starts installing what's new; the daemon restarts once it's installed and no run is in progress. 409:
        nothing to install, or it can't be installed here, with why."""
        try:
            return await updates.start()
        except UpdateError as e:
            raise HTTPException(409, str(e)) from e


def _add_log_routes(app: FastAPI, logs: Mapping[str, LogSource], streams: DeviceStreams) -> None:
    """The daemon's log (core/logs/): its files and its process output, the latest entries or followed live."""

    @app.get("/logs")
    async def logs_options() -> LogOptions:
        return await log_options(logs.values())

    @app.get("/logs/{name}")
    async def log_page(
        name: str,
        level: LogLevel | None = None,
        component: str = "",
        lines: Annotated[int, Query(ge=1, le=MAX_LINES)] = 100,
    ) -> LogPage:
        """The latest `lines` entries at `level` or above from `component`, oldest first. 400: an unknown component."""
        return await _log_source(logs, name).page(_log_query(level, component, lines))

    @app.get("/logs/{name}/follow", response_class=EventSourceResponse, responses=_EVENT_STREAM)
    async def follow_log(
        name: str,
        request: Request,
        level: LogLevel | None = None,
        component: str = "",
        lines: Annotated[int, Query(ge=1, le=MAX_LINES)] = 100,
    ) -> EventSourceResponse:
        """A `page` event like GET /logs/{name}, then an `entry` event for each new matching entry.
        Every connection, a reconnection too, starts with its page."""
        entries = _log_source(logs, name).follow(_log_query(level, component, lines))
        return EventSourceResponse(streams.guard(_log_events(entries), device_of(request)), ping=15)


def _add_log_level_routes(app: FastAPI, service: AssistantService) -> None:
    """The level the daemon records at (core/logs/level.py), applied without a restart."""

    @app.get("/settings/log-level")
    async def log_level() -> LogLevelSetting:
        return LogLevelSetting(level=await service.log_level())

    @app.put("/settings/log-level")
    async def set_log_level(body: LogLevelChange) -> LogLevelSetting:
        """400: an unknown level."""
        try:
            return LogLevelSetting(level=await service.set_log_level(body.level))
        except LogLevelError as e:
            raise HTTPException(400, str(e)) from e


def _add_language_routes(app: FastAPI, service: AssistantService) -> None:
    """The language of the apps' own text (core/language.py)."""

    @app.get("/settings/language")
    async def language() -> LanguageSetting:
        return LanguageSetting(language=await service.language())

    @app.put("/settings/language")
    async def set_language(body: LanguageChange) -> LanguageSetting:
        """400: an unknown language."""
        try:
            return LanguageSetting(language=await service.set_language(body.language))
        except LanguageError as e:
            raise HTTPException(400, str(e)) from e


def _add_dispatch_routes(app: FastAPI, service: AssistantService) -> None:
    """How sure routing a message from the inbox has to be (core/conversation/dispatch_setting.py)."""

    @app.get("/settings/dispatch")
    async def dispatch_setting() -> DispatchSetting:
        return await service.dispatch_setting()

    @app.put("/settings/dispatch")
    async def set_dispatch_setting(body: DispatchSetting) -> DispatchSetting:
        """400: a confidence outside 0 to 1."""
        try:
            return await service.set_dispatch_setting(body)
        except DispatchSettingError as e:
            raise HTTPException(400, str(e)) from e


def _log_source(logs: Mapping[str, LogSource], name: str) -> LogSource:
    if name not in logs:
        raise HTTPException(404, f"No log named {name}")
    return logs[name]


def _log_query(level: LogLevel | None, component: str, lines: int) -> LogQuery:
    try:
        return LogQuery(level or "", component, lines)
    except LogQueryError as e:
        raise HTTPException(400, str(e)) from e


async def _log_events(entries: AsyncGenerator[LogPage | LogEntry]):
    # Closed with the stream, so a followed journal's journalctl stops at once.
    async with contextlib.aclosing(entries):
        async for item in entries:
            kind = "entry" if isinstance(item, LogEntry) else "page"
            yield {"event": kind, "data": json.dumps(asdict(item))}


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


def _stream_key(request: Request) -> StreamKey:
    """Whose /events stream: a client's on its device, so no other device can send to it."""
    device = device_of(request)
    return device.id if device else "", _client_id(request)


def _client(request: Request) -> tuple[str, str, str, str]:
    """(id, kind, transport, device id). Connections on the Unix socket have no peer address and no device."""
    peer = request.client
    transport = f"{peer.host}:{peer.port}" if peer and peer.host else "unix socket"
    device = device_of(request)
    client_id, kind = request.headers.get(CLIENT_ID_HEADER, ""), request.headers.get(CLIENT_HEADER, "")
    return client_id, kind, transport, device.id if device else ""
