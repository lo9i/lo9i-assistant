"""Keeps the app running when the daemon can't be reached. Textual stops the app on any error a
handler raises, so every handler that calls the daemon is wrapped with `reports_daemon_unavailable`,
which shows the error as a notification instead. The user can retry once the daemon is back."""

from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, Concatenate

from textual.app import App
from textual.widget import Widget

from assistant.client import DaemonUnavailableError


def reports_daemon_unavailable[Owner: (Widget, App), **P](
    handler: Callable[Concatenate[Owner, P], Coroutine[Any, Any, None]],
) -> Callable[Concatenate[Owner, P], Coroutine[Any, Any, None]]:
    @wraps(handler)
    async def _handler(owner: Owner, *args: P.args, **kwargs: P.kwargs) -> None:
        try:
            await handler(owner, *args, **kwargs)
        except DaemonUnavailableError as e:
            owner.notify(str(e), title="Daemon unavailable", severity="error", timeout=10)

    return _handler
