"""Work an MCP server goes on with after a call returned, and tells lo9i about when it's finished
(docs/background-work.md). lo9i advertises the client extension `lo9i/background`. Each call the assistant
makes carries the conversation it's made in, `_meta["lo9i/origin"]`; the server keeps it with the work and
sends it back in `notifications/lo9i/work_finished`, whose end is then told like a coding agent's task's
(core/background.py). Between `notifications/lo9i/work_started` and the end, a server that runs on demand
(core/mcp/on_demand.py) isn't stopped as idle."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict
from typing import Any

from mcp.client.extension import ClientExtension, NotificationBinding
from mcp.types import RequestParamsMeta
from pydantic import BaseModel, Field

from assistant.core.background import Ended, Origin, short
from assistant.core.hidden_text import strip_hidden

EXTENSION = "lo9i/background"
ORIGIN_META = "lo9i/origin"
STARTED = "notifications/lo9i/work_started"
FINISHED = "notifications/lo9i/work_finished"
# How much of the server's text the user's notification and the assistant's note show.
_NOTICE, _NOTE = 300, 1_000


class WorkStarted(BaseModel):
    # The server's name for the work, unique among its work in progress.
    work: str = Field(min_length=1, max_length=200)


class WorkFinished(BaseModel):
    work: str = Field(min_length=1, max_length=200)
    # The `_meta["lo9i/origin"]` of the call that started the work, as it came.
    origin: Origin
    ok: bool = True
    # What came of it, or what went wrong.
    text: str


class BackgroundWork(ClientExtension):
    identifier = EXTENSION

    def __init__(
        self, started: Callable[[WorkStarted], Awaitable[None]], finished: Callable[[WorkFinished], Awaitable[None]]
    ) -> None:
        self._started = started
        self._finished = finished

    def notifications(self) -> Sequence[NotificationBinding[Any]]:
        return [
            NotificationBinding(method=STARTED, params_type=WorkStarted, handler=self._started),
            NotificationBinding(method=FINISHED, params_type=WorkFinished, handler=self._finished),
        ]


def origin_meta(origin: Origin | None) -> RequestParamsMeta | None:
    """The `_meta` of a call made in `origin`'s conversation; None outside a run."""
    if origin is None:
        return None
    meta: RequestParamsMeta = {}
    meta[ORIGIN_META] = asdict(origin)
    return meta


def ended(server: str, finished: WorkFinished) -> Ended:
    """The server's text is cleaned like its tools' results and said to be the server's."""
    text = strip_hidden(finished.text)
    notice = f"{'✅' if finished.ok else '⚠️'} {server}: {short(text, _NOTICE)}"
    outcome = "finished" if finished.ok else "failed"
    note = f"The MCP server {server} says its background work {finished.work} {outcome}: {short(text, _NOTE)}"
    return Ended(f"mcp:{server}:{finished.work}", finished.ok, notice, note)
