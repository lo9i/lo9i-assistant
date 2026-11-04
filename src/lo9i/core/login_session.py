"""The user's login session on macOS, for a daemon started at boot outside it (a LaunchDaemon, daemon/launchd.py).
Such a daemon has no screen, so `open` can't show an app, and no ssh agent. The session helper (lo9i/session/)
runs in the session as a LaunchAgent while the user is logged in (daemon/session_agent.py) and does both for it:

- A plugin that declares `login_session: true` in its server.yaml gets the helper's socket in `ENV`, where it asks
  the helper to open a link or an app on the screen (docs/login-session.md). A daemon in the session (started by
  hand, by the terminal app) gives it nothing: the plugin opens it itself.
- The helper links the session's ssh agent at `ssh_agent_link()`, which plugins that ask for the ssh agent get
  instead of the daemon's own (core/mcp/ssh_agent.py).

While nobody is logged in there's no helper: opening fails with the plugin saying so, and the link leads nowhere."""

import os
import sys
from dataclasses import replace
from pathlib import Path

from lo9i.core.config import settings
from lo9i.core.i18n import said
from lo9i.core.mcp.servers import McpServer

# launchd marks the daemons it starts from boot with it (daemon/launchd.py).
FROM_BOOT_ENV = "LO9I_LAUNCHD"
# The helper's socket, for a plugin that declares `login_session: true`.
ENV = "LO9I_LOGIN_SESSION"


def from_boot() -> bool:
    """Whether this daemon runs outside the user's login session: macOS's launchd started it at boot."""
    return sys.platform == "darwin" and os.environ.get(FROM_BOOT_ENV) == "1"


def socket_path() -> Path:
    return Path(settings.session_socket).expanduser()


def ssh_agent_link() -> Path:
    """Where the helper links the session's ssh agent; it leads nowhere while nobody is logged in."""
    return socket_path().with_name("ssh-agent.sock")


def parse(value: object) -> bool:
    """Raises ValueError for anything but true or false."""
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError(said("its login_session must be true or false"))
    return value


def with_session(server: McpServer) -> McpServer:
    """The server with the helper's socket in its env when it asks for the login session and the daemon is outside
    it."""
    if not (server.login_session and from_boot()):
        return server
    return replace(server, env={**server.env, ENV: str(socket_path())})
