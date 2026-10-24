"""The HTTPS listener for browsers on other hosts (settings `https_*`), and picking up a renewed
certificate without a restart."""

import logging
from pathlib import Path

from watchfiles import awatch

from assistant.core.config import settings
from assistant.daemon.http_server import HttpServer, Listener

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return settings.https_port > 0


def listener(port: int) -> Listener:
    """Where and with what to listen, on this port (the API's, or the pages' next to it)."""
    return Listener(
        host=settings.https_bind, port=port, certfile=_path(settings.https_cert), keyfile=_path(settings.https_key)
    )


async def reload_on_renewal(*servers: HttpServer) -> None:
    """Loads the certificate again whenever its folder changes. Certificate tools (certbot,
    acme.sh) write renewals into place, often by swapping symlinks, so the folder is watched
    rather than the file. New connections get the new certificate; open ones keep theirs."""
    folders = {str(Path(_path(settings.https_cert)).parent), str(Path(_path(settings.https_key)).parent)}
    async for _ in awatch(*folders):
        for server in servers:
            _reload(server)


def _reload(server: HttpServer) -> None:
    try:
        server.reload_certificate(_path(settings.https_cert), _path(settings.https_key))
    except (OSError, ValueError) as e:
        # Mid-renewal the files can be briefly inconsistent; the next change loads them again.
        logger.warning("Couldn't load the renewed certificate yet: %s", e)
        return
    logger.info("Loaded the renewed HTTPS certificate.")


def _path(value: str) -> str:
    return str(Path(value).expanduser())
