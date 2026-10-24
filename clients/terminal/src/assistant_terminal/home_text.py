"""Home (core/home/) as text, for the /home screen: when each item is, a section's last result, and when the
page was last updated, as the web app's Home page shows them (lib/home.ts)."""

from datetime import date, datetime

from assistant.core.agent import HomeCard, HomeItem


def item_when(item: HomeItem, today: date) -> str:
    """When an item is, seen from `today`: "09:00", "Tomorrow 21:00", "Fri 24 Oct", or "" for one without either."""
    if not item.date or item.date == today.isoformat():
        return item.time or ("Today" if item.date else "")
    day = _day_name(date.fromisoformat(item.date), today)
    return f"{day} {item.time}" if item.time else day


def _day_name(day: date, today: date) -> str:
    days = (day - today).days
    if days == 1:
        return "Tomorrow"
    if days == -1:
        return "Yesterday"
    return day.strftime("%a %d %b")


def describe(card: HomeCard, today: date) -> str:
    """A section's last result: its items with when each is, its note, and why it failed or wasn't built."""
    result = card.result
    if result is None:
        return "Not built yet: Refresh builds it."
    lines = [_problem(result.status, result.error)] if result.status != "ok" else []
    lines += [_item(item, today) for item in result.items]
    if result.note:
        lines.append(f"_{result.note}_")
    if not result.items and not result.note and result.status == "ok":
        lines.append("Nothing to show.")
    return "\n".join(lines)


def _item(item: HomeItem, today: date) -> str:
    when = item_when(item, today)
    parts = [f"**{item.title}**", *([item.subtitle] if item.subtitle else []), *([when] if when else [])]
    return f"- {' · '.join(parts)}"


def _problem(status: str, error: str) -> str:
    if status == "unavailable":
        return f"**Not built:** {error or 'none of its plugins is installed and on.'}\n"
    return f"**Couldn't build it:** {error or 'no reason given.'} What it showed before stays.\n"


def updated(at: str, now: datetime) -> str:
    """When the page was last updated: "Updated 10:32" today, "Updated Wed 21 Oct 18:05" before; "" before the
    first refresh."""
    if not at:
        return ""
    when = datetime.fromisoformat(at).astimezone(now.tzinfo)
    return f"Updated {when.strftime('%H:%M' if when.date() == now.date() else '%a %d %b %H:%M')}"
