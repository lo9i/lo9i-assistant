"""What Home is made of: its sections (the user's instructions) and each one's result, in one format for
every section, which the apps draw without knowing what the section is about."""

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# The widest a card can be: the columns the web app's Home has room for at its widest.
MAX_COLUMNS = 4
_URL = re.compile(r"^https?://\S+$")


class HomeItem(BaseModel):
    """One thing the section shows: an event, an episode, a bill."""

    title: str = Field(description="What it is, in a few words: the event, the show or movie, the bill.")
    subtitle: str = Field(default="", description="One short line more, or empty: where, which episode, how much.")
    date: str = Field(default="", description="Its day as YYYY-MM-DD, or empty when it has none.")
    time: str = Field(default="", description="Its time of day as HH:MM, 24-hour, or empty when it has none.")
    url: str = Field(
        default="",
        description="The full http(s) address that opens it (the story, the event's page) when one was found, "
        "or empty. Only here, never in the title or subtitle.",
    )

    @field_validator("date")
    @classmethod
    def _a_day(cls, value: str) -> str:
        if value and not _DAY.match(value):
            raise ValueError(f"{value!r} isn't a day as YYYY-MM-DD")
        if value:
            dt.date.fromisoformat(value)
        return value

    @field_validator("time")
    @classmethod
    def _a_time(cls, value: str) -> str:
        if value and not _TIME.match(value):
            raise ValueError(f"{value!r} isn't a time as HH:MM")
        return value

    @field_validator("url")
    @classmethod
    def _a_link(cls, value: str) -> str:
        if value and not _URL.match(value):
            raise ValueError(f"{value!r} isn't an http(s) address")
        return value


class SectionContent(BaseModel):
    """What one section of the user's Home page shows."""

    items: list[HomeItem] = Field(description="What was found, in the order to show it; empty for nothing.")
    note: str = Field(default="", description="One short line, or empty: that there's nothing today, or what failed.")


class HomeSection(BaseModel):
    """A section as the user wrote it."""

    # Unique within Home; "" for a new section, which gets one when saved.
    id: str = ""
    title: str
    # What to show, for the assistant.
    prompt: str
    # The plugins whose tools it reads; empty for every plugin's.
    plugins: list[str] = []
    # How many of the page's columns its card spans where the page has them: 0 for the apps to choose (two for a
    # busy one), up to MAX_COLUMNS.
    columns: int = Field(default=0, ge=0, le=MAX_COLUMNS)


# ok: built. unavailable: none of its plugins is installed and on, so it wasn't built. failed: building it failed;
# the items are the last ones that were built.
Status = Literal["ok", "unavailable", "failed"]


class SectionResult(BaseModel):
    section_id: str
    title: str
    status: Status
    items: list[HomeItem] = []
    note: str = ""
    # Why it failed or wasn't built.
    error: str = ""
    # The plugin whose web page the section links to; "" for none.
    page: str = ""
    # When it was built or tried, ISO 8601.
    at: str


class HomeCard(BaseModel):
    section: HomeSection
    # None until it's built the first time.
    result: SectionResult | None = None


class HomePage(BaseModel):
    cards: list[HomeCard]
    # When the last refresh of every section ended, ISO 8601; "" before the first.
    updated_at: str = ""
    # A refresh is running; each section's result is saved as it's ready.
    refreshing: bool = False
