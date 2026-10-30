"""Connections to a model provider that notice when they died.

A computer that sleeps freezes the daemon, and its timeouts count only time awake: asyncio's clock
(mach_absolute_time on macOS) stops while it sleeps. A connection open across the sleep is usually dead on
waking (the provider closed it, and the close was lost), and nothing tells the client: a call waiting on it
sees its 600s read timeout only after 600s awake, which takes hours on a laptop that wakes for a few seconds
now and then. On 2026-10-12 a memory digest waited that way from 23:05 until a restart the next morning.

TCP keepalive probes the provider once the connection has been idle a short while, so a dead one fails
within about a minute of being awake, and the SDK retries the call on a new connection. Anthropic's SDK turns keepalive
on itself, but sets no idle time on macOS, which then waits the system's two hours before the first probe."""

import socket
import sys

import httpx
import httpx2

# Model calls can stream for minutes; connecting shouldn't take long.
MODEL_TIMEOUT = httpx.Timeout(600, connect=30)
_IDLE_SECONDS = 30
_PROBE_SECONDS = 10
_PROBES = 3

# Linux and macOS name the idle time before the first probe differently.
_IDLE_OPTION = socket.TCP_KEEPALIVE if sys.platform == "darwin" else socket.TCP_KEEPIDLE


def socket_options() -> list[tuple[int, int, int]]:
    return [
        (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
        (socket.IPPROTO_TCP, _IDLE_OPTION, _IDLE_SECONDS),
        (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, _PROBE_SECONDS),
        (socket.IPPROTO_TCP, socket.TCP_KEEPCNT, _PROBES),
    ]


def transport() -> httpx.AsyncHTTPTransport:
    """A transport for one HTTP client to a model provider."""
    return httpx.AsyncHTTPTransport(socket_options=socket_options())


def client() -> httpx.AsyncClient:
    """An HTTP client for a model provider's SDK, as the Copilot model has (core/llm/copilot.py)."""
    return httpx.AsyncClient(transport=transport(), timeout=MODEL_TIMEOUT)


def httpx2_client() -> httpx2.AsyncClient:
    """The same for an SDK built on httpx2 (Anthropic's), which refuses httpx's clients."""
    transport = httpx2.AsyncHTTPTransport(socket_options=socket_options())
    return httpx2.AsyncClient(transport=transport, timeout=httpx2.Timeout(600, connect=30), follow_redirects=True)
