"""Blocks fetches to private and internal addresses (W2).

The agent runs in the same Docker network as Postgres and SearXNG, so a page must not be able
to point it at internal services. Each redirect hop is checked too (see fetch.py). A DNS answer
that changes between this check and the request is not covered.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

_BLOCKED_HOSTS = {"localhost", "metadata.google.internal"}


class UnsafeUrlError(Exception):
    pass


async def check_url(url: str) -> None:
    """Raises UnsafeUrlError unless the URL is http(s) and every address it resolves to is public."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeUrlError(f"Only http and https URLs can be fetched: {url}")
    host = parts.hostname.lower()
    if host in _BLOCKED_HOSTS:
        raise UnsafeUrlError(f"Blocked host: {host}")
    for address in await _resolve(host, parts.port):
        if not ipaddress.ip_address(address).is_global:
            raise UnsafeUrlError(f"{host} resolves to a private or internal address ({address})")


async def _resolve(host: str, port: int | None) -> set[str]:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise UnsafeUrlError(f"Can't resolve {host}") from e
    return {str(info[4][0]).split("%")[0] for info in infos}
