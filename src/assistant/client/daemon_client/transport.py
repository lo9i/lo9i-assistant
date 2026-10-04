from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any

import httpx

from assistant.client.errors import DaemonUnavailableError
from assistant.protocol import CLIENT_ID_HEADER


class Transport:
    """The HTTP connection shared by every part of the client. Error responses become the same
    exceptions the service raises."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        # How the daemon's list of connected clients names this one.
        self.client_id = http.headers.get(CLIENT_ID_HEADER, "")

    async def request(
        self,
        method: str,
        path: str,
        *,
        errors: Mapping[int, type[Exception]] | None = None,
        timeout: httpx.Timeout | None = None,
        **kwargs: Any,
    ) -> Any:
        """The JSON response. Status codes listed in `errors` raise that exception with the
        daemon's `detail` message; any other error status raises httpx.HTTPStatusError. Raises
        DaemonUnavailableError when the daemon can't be reached."""
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.TransportError as e:
            raise DaemonUnavailableError(f"Can't reach the daemon: {e}") from e
        error = (errors or {}).get(response.status_code)
        if error is not None:
            raise error(response.json()["detail"])
        response.raise_for_status()
        return response.json()

    async def content(
        self, path: str, *, params: Mapping[str, str], errors: Mapping[int, type[Exception]] | None = None
    ) -> bytes:
        """A response's body as bytes (a file), with the same errors as `request`."""
        try:
            response = await self._http.get(path, params=params)
        except httpx.TransportError as e:
            raise DaemonUnavailableError(f"Can't reach the daemon: {e}") from e
        error = (errors or {}).get(response.status_code)
        if error is not None:
            raise error(response.json()["detail"])
        response.raise_for_status()
        return response.content

    def stream(self, path: str, last_event_id: str) -> AbstractAsyncContextManager[httpx.Response]:
        """A Server-Sent Events response, resuming after `last_event_id` ("" to start fresh)."""
        headers = {"Last-Event-ID": last_event_id} if last_event_id else {}
        return self._http.stream("GET", path, headers=headers)
