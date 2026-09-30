"""Reading a daemon event stream that survives dropped connections: after a drop it reconnects
and resumes after the last event received, so nothing is missed or repeated."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from assistant.client.daemon_client.transport import Transport
from assistant.client.errors import DaemonUnavailableError
from assistant.client.sse import read_events


@dataclass(frozen=True)
class ReconnectPolicy:
    delay_seconds: float
    # Failed attempts in a row before giving up; None keeps trying for as long as the reader reads.
    attempts: int | None = None


async def resumable_events(transport: Transport, path: str, policy: ReconnectPolicy) -> AsyncIterator[tuple[str, str]]:
    """(event type, data) for the stream at `path`, until the caller stops reading. A connection
    that drops or ends is reopened. Raises DaemonUnavailableError when the policy gives up, and
    httpx.HTTPStatusError for a client error (4xx), which reconnecting can't fix."""
    last_id, failures = "0", 0
    while True:
        try:
            async with transport.stream(path, last_id) as response:
                response.raise_for_status()
                async for event_id, kind, data in read_events(response):
                    last_id, failures = event_id or last_id, 0
                    yield kind, data
        except httpx.HTTPStatusError as e:
            if e.response.is_client_error:
                raise
        except httpx.TransportError:
            pass
        failures += 1
        await _wait_or_give_up(policy, failures)


async def _wait_or_give_up(policy: ReconnectPolicy, failures: int) -> None:
    if policy.attempts is not None and failures >= policy.attempts:
        raise DaemonUnavailableError("Lost the connection to the daemon.")
    await asyncio.sleep(policy.delay_seconds)
