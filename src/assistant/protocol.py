"""How events and status objects travel between the daemon and its clients: plain JSON dicts
with a "type" field naming the event class."""

from dataclasses import asdict
from typing import Any

from assistant.core import events
from assistant.core.events import Event

_EVENT_TYPES = {cls.__name__: cls for cls in (
    events.TextDelta, events.ToolStarted, events.ToolFinished, events.ApprovalRequired,
    events.Transcribed, events.Done, events.Error,
)}

# Sent after a run's last event, so clients know the stream is complete.
END = "end"

# Every client request carries this header (see daemon/api.py for why).
CLIENT_HEADER = "X-Lo9i-Client"


def event_to_dict(event: Event) -> dict[str, Any]:
    return {"type": type(event).__name__, **asdict(event)}


def event_from_dict(data: dict[str, Any]) -> Event:
    fields = {k: v for k, v in data.items() if k != "type"}
    return _EVENT_TYPES[data["type"]](**fields)
