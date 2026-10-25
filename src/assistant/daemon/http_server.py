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

from hypercorn.asyncio.run import worker_serve
from hypercorn.config import Config, Sockets
from hypercorn.typing import Framework
from hypercorn.utils import wrap_app

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
        self._listener = listener
        self._sockets: Sockets | None = None

    @property
    def address(self) -> str:
        return self._listener.address

    def bind(self) -> None:
        """Binds the listener and listens now, before `serve`: the daemon says it's ready only once each one is,
        and a failure here is the daemon's to handle, not lost in the task `serve` runs in. Connections that come
        before `serve` accepts wait in the backlog. Raises OSError when it can't bind (the port is taken)."""
        self._sockets = self._config.create_sockets()
        for sock in [*self._sockets.secure_sockets, *self._sockets.insecure_sockets]:
            sock.listen(self._config.backlog)

    def unbind(self) -> None:
        """Lets go of what `bind` bound, for a daemon that won't serve after all."""
        if self._sockets is not None:
            for sock in [*self._sockets.secure_sockets, *self._sockets.insecure_sockets, *self._sockets.quic_sockets]:
                sock.close()
            self._sockets = None

    async def serve(self, stop: asyncio.Event) -> None:
        """Serves until `stop` is set, on the sockets `bind` bound, or binding them itself."""
        app = wrap_app(self._app, self._config.wsgi_max_body_size, None)
        await worker_serve(app, self._config, sockets=self._sockets, shutdown_trigger=stop.wait)

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
