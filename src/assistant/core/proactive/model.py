"""What the assistant's own initiative is made of: its settings, the open loops it keeps, the briefings it sends and
the reviews it writes, and what the models answer when writing them."""

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Kinds of suggestion the user can mute, at most.
MAX_MUTED = 50
_KIND_CHARS = 60


def _a_time(value: str) -> str:
    if not _TIME.match(value):
        raise ValueError(f"{value!r} isn't a time as HH:MM")
    return value


def a_kind(text: str) -> str:
    """A kind as kept and compared: lowercase, one space between words, cut."""
    return " ".join(text.lower().split())[:_KIND_CHARS]


class ProactiveSettings(BaseModel):
    """On by default, at the user's times (their time zone, settings.timezone)."""

    briefing: bool = True
    briefing_time: str = "08:00"
    nightly: bool = True
    nightly_time: str = "23:00"
    # The weekly review runs after the nightly one of its day (0 Monday to 6 Sunday), or at the nightly time.
    weekly: bool = True
    weekly_day: int = Field(default=6, ge=0, le=6)
    # Reminders of open loops sent at their time, between the briefing time and the nightly time, a few a day.
    reminders: bool = True
    # Kinds of suggestion the user doesn't want ("automation suggestions"), never made again until removed.
    muted: list[str] = []

    @field_validator("briefing_time", "nightly_time")
    @classmethod
    def _times(cls, value: str) -> str:
        return _a_time(value)

    @field_validator("muted")
    @classmethod
    def _kinds(cls, value: list[str]) -> list[str]:
        kinds = list(dict.fromkeys(k for k in map(a_kind, value) if k))
        if len(kinds) > MAX_MUTED:
            raise ValueError(f"at most {MAX_MUTED} muted kinds")
        return kinds


LoopStatus = Literal["open", "done", "dismissed"]
# conversation: an archived part of one said it's still to do (core/conversation/digest.py); review: the nightly or
# weekly review found it; briefing: the briefing found it in the plugins (a bill due); assistant: the assistant
# added it in a conversation, when the user asked.
LoopSource = Literal["conversation", "review", "briefing", "assistant"]


class OpenLoop(BaseModel):
    """Something still to do, waiting on someone, or promised to the user."""

    id: str
    text: str
    # What kind of thing it is ("bill due", "unanswered mail"), for muting; "" for none.
    kind: str = ""
    source: LoopSource
    # The conversation it came from, to open it; "" for none.
    thread_id: str = ""
    # ISO 8601.
    created_at: str
    status: LoopStatus = "open"
    closed_at: str = ""
    # The day it's due (YYYY-MM-DD), or "".
    due: str = ""
    # When to remind the user (ISO 8601, UTC), or ""; reminded_at once the reminder went.
    remind_at: str = ""
    reminded_at: str = ""
    # What it's known by: a loop is added once per key, so one closed or dismissed doesn't come back.
    key: str
    # The plugin whose list for the day it came from (core/mcp/today.py), which closes it once the list no longer has
    # it (the bill was paid); "" for one from anywhere else.
    plugin: str = ""


class LoopDraft(BaseModel):
    """An open loop as a model writes it."""

    text: str = Field(description="What's open, in one short line the user understands on its own, in their language.")
    kind: str = Field(default="", description="Its kind in a few words, from the kinds listed when one fits.")
    key: str = Field(
        default="",
        description="What it's known by, so it isn't added twice: its subject and its date or month "
        "(electricity bill 2026-11, invoices 2026-10). Empty to use the text.",
    )
    due: str = Field(default="", description="The day it's due as YYYY-MM-DD, or empty.")
    remind_at: str = Field(
        default="",
        description="Only when it's urgent and has a time: when to remind the user, as local YYYY-MM-DDTHH:MM. "
        "Usually empty: the briefing lists it.",
    )

    @field_validator("due")
    @classmethod
    def _a_day(cls, value: str) -> str:
        if value and not _DAY.match(value):
            raise ValueError(f"{value!r} isn't a day as YYYY-MM-DD")
        if value:
            dt.date.fromisoformat(value)
        return value

    @field_validator("remind_at")
    @classmethod
    def _a_moment(cls, value: str) -> str:
        if value:
            dt.datetime.fromisoformat(value)
        return value


class Suggestion(BaseModel):
    kind: str = Field(description="Its kind in a few words, from the kinds listed when one fits.")
    text: str = Field(description="The suggestion in one or two short lines, in the user's language.")


class MailPick(BaseModel):
    account: str = Field(description="Its account, as given in brackets.")
    uid: int = Field(description="Its uid, as given in brackets.")
    line: str = Field(description="Who wrote and what about, in a few words in the user's language.")
    asks: bool = Field(description="Whether it asks the user something or waits for their answer.")


class MailDraft(BaseModel):
    """What the briefing's one model call answers: which unread mail matters."""

    important: list[MailPick] = Field(
        default=[],
        description="At most five messages from people worth the user's attention today, the most important first; "
        "none from newsletters, notifications, receipts or ads. Usually few or none.",
    )


class ReviewDraft(BaseModel):
    """What the nightly or weekly review model writes."""

    summary: str = Field(description="The period in two or three short lines, for the next reviews.")
    new_loops: list[LoopDraft] = Field(default=[], description="What's left open that isn't an open loop yet.")
    done_loop_ids: list[str] = Field(default=[], description="Ids of open loops the period shows are done.")
    habits: list[str] = Field(
        default=[], description="Lasting patterns in how the user lives or works, not saved yet; usually none."
    )
    suggestions: list[Suggestion] = Field(default=[], description="At most three suggestions for the next briefing.")


BriefingStatus = Literal["sent", "nothing", "failed"]


class Briefing(BaseModel):
    # The user's day it was for (YYYY-MM-DD) and when it was written (ISO 8601).
    day: str
    at: str
    status: BriefingStatus
    text: str = ""
    # The chat channels that took it; none means it's only in the notifications feed.
    channels: list[str] = []
    error: str = ""


ReviewKind = Literal["nightly", "weekly"]


class Review(BaseModel):
    kind: ReviewKind
    day: str
    at: str
    summary: str = ""
    suggestions: list[Suggestion] = []
    habits: list[str] = []
    # Open loops it added and closed.
    added: int = 0
    closed: int = 0
    # Its suggestions went into a briefing.
    briefed: bool = False
    error: str = ""


class ProactivePage(BaseModel):
    """What the apps show: the settings, the loops, the latest briefing and reviews, and what runs now."""

    settings: ProactiveSettings
    loops: list[OpenLoop]
    briefing: Briefing | None = None
    reviews: list[Review] = []
    # A briefing or review running now.
    running: list[Literal["briefing", "nightly", "weekly"]] = []
