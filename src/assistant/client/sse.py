"""Reads a Server-Sent Events stream into (id, event type, data) tuples."""

from collections.abc import AsyncIterator

import httpx


async def read_events(response: httpx.Response) -> AsyncIterator[tuple[str, str, str]]:
    event_id, event_type, data = "", "message", []
    async for line in response.aiter_lines():
        if not line:
            if data:
                yield event_id, event_type, "\n".join(data)
            event_type, data = "message", []
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "id":
            event_id = value
        elif field == "event":
            event_type = value
        elif field == "data":
            data.append(value)
