"""The daemon's HTTP servers, on Hypercorn: the API on the Unix socket, localhost and HTTPS, and the plugins'
pages on the next ports (daemon/pages.py).

Over TLS a browser and Hypercorn agree on HTTP/2 (ALPN), so a page's requests, its event streams and its
WebSockets share one connection, instead of queuing for the six connections per site HTTP/1.1 allows a
browser. Plain HTTP on localhost and on the Unix socket stays HTTP/1.1: browsers speak HTTP/2 only over TLS.

Signals are the daemon's own (server.py): a server stops accepting once `stop` is set, and gives the requests
in progress `GRACEFUL_SECONDS` to end. Event streams end on their own first (server.py sets sse_starlette's
AppStatus)."""

import asyncio
import logging
from dataclasses import dataclass
from ssl import SSLContext
from typing import Any, cast

from hypercorn.asyncio import serve
from hypercorn.config import Config
from hypercorn.typing import Framework

# Long enough for the answer to a restart or stop to go out, and for a request in progress to end.
GRACEFUL_SECONDS = 10


@dataclass(frozen=True)
class Listener:
    """Where a server listens: a Unix socket, or a host and port, with a certificate for HTTPS."""

    socket: str = ""
    host: str = ""
    port: int = 0
    certfile: str = ""
    keyfile: str = ""

    @property
    def address(self) -> str:
        """As Hypercorn binds it: unix:<path>, host:port, or [host]:port for IPv6."""
        if self.socket:
            return f"unix:{self.socket}"
        return f"[{self.host}]:{self.port}" if ":" in self.host else f"{self.host}:{self.port}"


class HttpServer:
    def __init__(self, app: Any, listener: Listener) -> None:
        self._app = cast(Framework, app)
        self._config = _Config(listener)

    async def serve(self, stop: asyncio.Event) -> None:
        await serve(self._app, self._config, shutdown_trigger=stop.wait)

    def reload_certificate(self, certfile: str, keyfile: str) -> None:
        """Loads a renewed certificate: new connections get it, open ones keep theirs. Raises OSError or
        ValueError for files that can't be loaded (yet)."""
        if self._config.context is not None:
            self._config.context.load_cert_chain(certfile, keyfile)


class _Config(Config):
    """Hypercorn's settings for one listener, keeping the TLS context it serves with, to load a renewed
    certificate into."""

    def __init__(self, listener: Listener) -> None:
        super().__init__()
        self.bind = [listener.address]
        self.certfile = listener.certfile or None
        self.keyfile = listener.keyfile or None
        self.graceful_timeout = GRACEFUL_SECONDS
        # Its records go to the daemon's log files like any other (core/logs/).
        self.accesslog = None
        self.errorlog = logging.getLogger("hypercorn.error")
        self.context: SSLContext | None = None

    def create_ssl_context(self) -> SSLContext | None:
        self.context = super().create_ssl_context()
        return self.context
