"""How events and status objects travel between the daemon and its clients: plain JSON dicts
with a "type" field naming the event class."""

from dataclasses import asdict, dataclass, field
from typing import Any

from assistant.core import events
from assistant.core.events import Event

_EVENT_TYPES = {
    cls.__name__: cls
    for cls in (
        events.TextDelta,
        events.Thinking,
        events.ToolStarted,
        events.ToolFinished,
        events.UserSaid,
        events.UserTaken,
        events.ApprovalRequired,
        events.Transcribed,
        events.Dispatched,
        events.Held,
        events.Done,
        events.Error,
        events.Cancelled,
    )
}

# Sent after a run's last event, so clients know the stream is complete.
END = "end"

# Every client request carries this header (see daemon/api.py for why). Its value is the kind of client.
CLIENT_HEADER = "X-Lo9i-Client"
# Tells apart two clients of the same kind, so a client can find itself in the list of connected clients.
CLIENT_ID_HEADER = "X-Lo9i-Client-Id"
# A client on a second conversation at once (the web app's voice button) sends its id, this, and a
# name for it ("<id>/voice"). That conversation belongs to the client's connection.
CLIENT_ID_PART = "/"
# The language an app shows its text in, when it settles auto itself (the web app follows the browser's): the
# daemon writes its errors in it (core/language.py::answered_in).
LANGUAGE_HEADER = "X-Lo9i-Language"


def event_to_dict(event: Event) -> dict[str, Any]:
    return {"type": type(event).__name__, **asdict(event)}


def event_from_dict(data: dict[str, Any]) -> Event:
    fields = {k: v for k, v in data.items() if k != "type"}
    return _EVENT_TYPES[data["type"]](**fields)


@dataclass
class ShutdownStatus:
    """A requested restart or stop: the daemon restarts or stops once these runs end, at once when none."""

    waiting_for_runs: int


@dataclass
class PendingEnding:
    """The restart or stop waiting for runs to end, and for an update being installed; `ending` is "" when none
    is. `can_take_back` is false when something needs it, which `needed_by` says ("An update was installed")."""

    ending: str
    waiting_for_runs: int
    waiting_for_update: bool = False
    can_take_back: bool = False
    needed_by: str = ""


class NoEndingError(Exception):
    """No restart or stop is waiting for runs: none was asked for, or it already went ahead."""


@dataclass
class StartupStatus:
    """Whether the daemon starts at boot, and whether this daemon was started that way."""

    enabled: bool
    managed: bool
    includes_ollama: bool
    # How it starts at boot: macos (LaunchDaemons), linux (a systemd user service) or unsupported.
    platform: str = "macos"
    # False on Linux while lingering is off: the service then runs only while the user is logged in.
    starts_without_login: bool = True
    # Why what's installed isn't what turning it on installs now (an older LaunchDaemon); empty when it is. Installing
    # it again (POST /system/startup/reinstall) brings it up to date.
    outdated: list[str] = field(default_factory=list)


@dataclass
class HostStatus:
    """The computer the daemon runs on. Sizes in bytes, percentages 0-100, `load_average` over 1, 5 and
    15 minutes (empty where the system has none)."""

    os: str
    arch: str
    hostname: str
    python: str
    version: str
    cpu_cores: int
    cpu_percent: float
    memory_used: int
    memory_total: int
    disk_used: int
    disk_total: int
    uptime_seconds: int
    load_average: list[float]
    # Why the daemon can't be stopped from the apps now; "" when it can.
    stop_refusal: str = ""


class StartupError(Exception):
    """Enabling or disabling start at boot failed or was cancelled."""


@dataclass
class Commit:
    """A version of lo9i: a commit of its repository. `date` is the commit's, ISO 8601."""

    sha: str
    subject: str
    date: str


@dataclass
class UpdateStatus:
    """The version the daemon runs and whether a newer one can be installed from the app (daemon/updates.py).

    `installed_from`: "git" (a clone the app can update), "deployed" (copied from another computer by
    scripts/deploy.sh, updated from there) or "package" (neither, nothing to compare against).
    `state`: idle, checking, updating (`step` says what it does), failed (`error` says why) or restarting.
    `new`: the commits the update brings, newest first, as of the last check (`checked_at`, ISO 8601).
    `reason`: why it can't be updated from the app, when `can_update` is false."""

    installed_from: str
    current: Commit | None
    upstream: str
    behind: int
    new: list[Commit]
    checked_at: str
    can_update: bool
    reason: str
    state: str
    step: str
    error: str


class UpdateError(Exception):
    """An update can't start; the message says why."""


class StopRefusedError(Exception):
    """The daemon can't be stopped from the app; the message says why."""


@dataclass
class ConnectedClient:
    """A client holding the daemon's event stream open. `transport` is "unix socket" or host:port.
    `device_id` is the paired device it connected from (empty on the Unix socket), `thread_id` the
    conversation it's on (empty until it starts, resumes or writes to one)."""

    id: str
    kind: str
    transport: str
    connected_at: str
    device_id: str = ""
    thread_id: str = ""
