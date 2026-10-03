"""The HTTPS listener for browsers on other hosts (settings `https_*`), and picking up a renewed
certificate without a restart."""

import logging
from pathlib import Path
from typing import TypedDict

import uvicorn
from watchfiles import awatch

from assistant.core.config import settings

logger = logging.getLogger(__name__)


class Bind(TypedDict):
    """uvicorn.Config arguments."""

    host: str
    port: int
    ssl_certfile: str
    ssl_keyfile: str


def enabled() -> bool:
    return settings.https_port > 0


def bind() -> Bind:
    """Where and with what to listen."""
    return {
        "host": settings.https_bind,
        "port": settings.https_port,
        "ssl_certfile": _path(settings.https_cert),
        "ssl_keyfile": _path(settings.https_key),
    }


async def reload_on_renewal(*servers: uvicorn.Server) -> None:
    """Loads the certificate again whenever its folder changes. Certificate tools (certbot,
    acme.sh) write renewals into place, often by swapping symlinks, so the folder is watched
    rather than the file. New connections get the new certificate; open ones keep theirs."""
    folders = {str(Path(_path(settings.https_cert)).parent), str(Path(_path(settings.https_key)).parent)}
    async for _ in awatch(*folders):
        for server in servers:
            _reload(server)


def _reload(server: uvicorn.Server) -> None:
    if server.config.ssl is None:
        return
    try:
        server.config.ssl.load_cert_chain(_path(settings.https_cert), _path(settings.https_key))
    except (OSError, ValueError) as e:
        # Mid-renewal the files can be briefly inconsistent; the next change loads them again.
        logger.warning("Couldn't load the renewed certificate yet: %s", e)
        return
    logger.info("Loaded the renewed HTTPS certificate.")


def _path(value: str) -> str:
    return str(Path(value).expanduser())
