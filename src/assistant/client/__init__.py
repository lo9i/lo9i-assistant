"""Client for the daemon, used by the CLI and any other client: the HTTP API on the daemon's Unix
socket, plus what every client needs around it (following the live conversation, attaching files,
recording voice)."""

from assistant.client.connection import connect
from assistant.client.daemon_client import DaemonClient
from assistant.client.errors import DaemonUnavailableError

__all__ = ["DaemonClient", "DaemonUnavailableError", "connect"]
