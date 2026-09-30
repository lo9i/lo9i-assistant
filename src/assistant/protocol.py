"""How events and status objects travel between the daemon and its clients: plain JSON dicts
with a "type" field naming the event class."""

from dataclasses import asdict, dataclass
from typing import Any

from assistant.core import events
from assistant.core.events import Event

_EVENT_TYPES = {
    cls.__name__: cls
    for cls in (
        events.TextDelta,
        events.ToolStarted,
        events.ToolFinished,
        events.ApprovalRequired,
        events.Transcribed,
        events.Done,
        events.Error,
    )
}

# Sent after a run's last event, so clients know the stream is complete.
END = "end"

# Every client request carries this header (see daemon/api.py for why). Its value is the kind of client.
CLIENT_HEADER = "X-Lo9i-Client"
# Tells apart two clients of the same kind, so a client can find itself in the list of connected clients.
CLIENT_ID_HEADER = "X-Lo9i-Client-Id"


def event_to_dict(event: Event) -> dict[str, Any]:
    return {"type": type(event).__name__, **asdict(event)}


def event_from_dict(data: dict[str, Any]) -> Event:
    fields = {k: v for k, v in data.items() if k != "type"}
    return _EVENT_TYPES[data["type"]](**fields)


@dataclass
class StartupStatus:
    """Whether the daemon starts at boot (LaunchDaemon), and whether this daemon was started that way."""

    enabled: bool
    managed: bool
    includes_ollama: bool


class StartupError(Exception):
    """Enabling or disabling start at boot failed or was cancelled."""


@dataclass
class ConnectedClient:
    """A client holding the daemon's event stream open. `transport` is "unix socket" or host:port."""

    id: str
    kind: str
    transport: str
    connected_at: str
