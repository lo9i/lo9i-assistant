"""Client for the daemon, used by the CLI. It offers the same methods gateways used to call on
AssistantService, over HTTP on the daemon's Unix socket."""

from assistant.client.daemon_client import DaemonClient, connect

__all__ = ["DaemonClient", "connect"]
