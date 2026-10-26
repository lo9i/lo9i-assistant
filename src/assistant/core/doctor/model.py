"""What the doctor finds: causes of problems, the context a conversation starts with, and the day's report
comparing both with the day before."""

from typing import Literal

from pydantic import BaseModel

# log: records at WARNING or above in the daemon's log; conversation: what the checkpoints show.
CauseKind = Literal["log", "conversation"]
# Against the day before: new there, happening more than GROWING_TIMES as often, or neither.
Change = Literal["", "new", "growing"]


class ThreadRef(BaseModel):
    thread_id: str
    title: str
    # A scheduled job's run, which the apps open on the job (its conversation isn't listed); "" for a conversation.
    job: str = ""
    run_at: str = ""


class Cause(BaseModel):
    """One cause and how often it happened in the day. `id` stays the same across days and versions: it's made
    of the kind, the text with its numbers and ids left out, and where it happened, without line numbers."""

    id: str
    kind: CauseKind
    # The highest level of its records (WARNING, ERROR, CRITICAL); "" for a conversation's.
    level: str = ""
    # A log's: the last exception line, or the record's first line. A conversation's: what went wrong.
    title: str
    # A log's: the last frame in lo9i's code ("assistant/core/mcp/hub.py in _connect"), or the logger.
    where: str = ""
    count: int
    # ISO 8601: when it first and last happened in the day.
    first: str
    last: str
    # The latest record in full, or what a conversation shows, cut.
    example: str = ""
    # The conversations it happened in.
    threads: list[ThreadRef] = []
    change: Change = ""
    # How often it happened the day before.
    before: int = 0


class ContextPart(BaseModel):
    name: str
    tokens: int
    # The day before; None when there's no report from then, or it didn't have this part.
    before: int | None = None


class StartingContext(BaseModel):
    """The context a new conversation starts with, its system prompt and tool definitions, against the window
    the conversation's context is measured against (the chat's context bar)."""

    tokens: int
    window: int
    parts: list[ContextPart]
    # Over the share of the window that alerts.
    too_large: bool = False


class DoctorReport(BaseModel):
    # The day checked, in the user's time zone (ISO date).
    day: str
    # When it was checked (ISO 8601); a check of a day that ended covers it whole.
    at: str
    whole_day: bool
    causes: list[Cause]
    # Causes the day before had and this day doesn't.
    gone: list[Cause] = []
    # The day it was compared with (ISO date); "" when no earlier day was checked.
    compared_with: str = ""
    context: StartingContext
    # Causes left out as known noise.
    known: int = 0
    # The alerts the user dismissed: cause ids, and CONTEXT_ALERT.
    dismissed: list[str] = []


class KnownCause(BaseModel):
    """Recurring noise that isn't a problem: left out of every report from then on."""

    id: str
    kind: CauseKind
    title: str
    where: str = ""
    # When it was marked (ISO 8601).
    at: str


class DoctorAlert(BaseModel):
    """A cause that's new or growing, or the context over the share of the window that alerts."""

    # A cause's id, or CONTEXT_ALERT.
    name: str
    kind: Literal["new", "growing", "context"]
    title: str
    text: str
    count: int
    at: str


class DoctorPage(BaseModel):
    """The latest report, the causes marked as known, and whether a check runs now."""

    report: DoctorReport | None
    known: list[KnownCause]
    checking: bool = False
