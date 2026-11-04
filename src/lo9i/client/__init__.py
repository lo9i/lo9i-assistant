"""Client for the daemon, used by the CLI and any other client: the HTTP API on the daemon's Unix
socket, plus what every client needs around it (following the live conversation, attaching files,
pasting from the clipboard, recording voice)."""

from lo9i.client.connection import connect
from lo9i.client.daemon_client import DaemonClient
from lo9i.client.errors import DaemonUnavailableError

__all__ = ["DaemonClient", "DaemonUnavailableError", "connect"]
