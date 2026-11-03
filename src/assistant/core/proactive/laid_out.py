"""The briefing as text, laid out by code: a heading per part, a line per thing, so no model writes it. Plain text, read
on a phone in a chat."""

from dataclasses import dataclass
from datetime import date

from assistant.core.i18n import Texts
from assistant.core.mcp.today import TodayItem
from assistant.core.proactive.model import OpenLoop


@dataclass(frozen=True)
class Part:
    heading: str
    lines: list[str]


def item_line(t: Texts, item: TodayItem, today: date) -> str:
    """Its day when it isn't today, its time, what it is, and what needs doing about it."""
    day = t.day(date.fromisoformat(item.date)) if item.date and item.date != today.isoformat() else ""
    what = " · ".join(filter(None, [item.title, item.subtitle]))
    line = " ".join(filter(None, [day, item.time, what]))
    return f"{line} → {item.needs}" if item.needs else line


def loop_line(t: Texts, loop: OpenLoop) -> str:
    return loop.text + (t(" (due {day})", day=t.day(date.fromisoformat(loop.due))) if loop.due else "")


def compose(parts: list[Part]) -> str:
    """The parts that have lines; "" when none has."""
    shown = [p for p in parts if p.lines]
    return "\n\n".join("\n".join([p.heading, *(f"- {line}" for line in p.lines)]) for p in shown)
