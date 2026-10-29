"""Home (core/home/) as text, for the /home screen: when each item is, a section's last result, and when the
page was last updated, as the web app's Home page shows them (lib/home.ts)."""

import re
from datetime import date, datetime

from assistant.core.agent import HomeCard, HomeItem
from assistant_terminal.i18n import short_date, t

# An address written in the subtitle, with the separator before it, for results built before items had a url.
_URL_IN_TEXT = re.compile(r"\s*(?:[·|,;-]\s*)?(https?://\S+)")


def item_when(item: HomeItem, today: date) -> str:
    """When an item is, seen from `today`: "09:00", "Tomorrow 21:00", "Fri 24 Oct", or "" for one without either."""
    if not item.date or item.date == today.isoformat():
        return item.time or (t("Today") if item.date else "")
    day = _day_name(date.fromisoformat(item.date), today)
    return f"{day} {item.time}" if item.time else day


def _day_name(day: date, today: date) -> str:
    days = (day - today).days
    if days == 1:
        return t("Tomorrow")
    if days == -1:
        return t("Yesterday")
    return short_date(day)


def describe(card: HomeCard, today: date) -> str:
    """A section's last result: its items with when each is, its note, and why it failed or wasn't built."""
    result = card.result
    if result is None:
        return t("Not built yet: Refresh builds it.")
    lines = [_problem(result.status, result.error)] if result.status != "ok" else []
    lines += [_item(item, today) for item in result.items]
    if result.note:
        lines.append(f"_{result.note}_")
    if not result.items and not result.note and result.status == "ok":
        lines.append(t("Nothing to show."))
    return "\n".join(lines)


def _item(item: HomeItem, today: date) -> str:
    when = item_when(item, today)
    subtitle, url = _linked(item)
    title = f"[**{item.title}**]({url})" if url else f"**{item.title}**"
    parts = [title, *([subtitle] if subtitle else []), *([when] if when else [])]
    return f"- {' · '.join(parts)}"


def _linked(item: HomeItem) -> tuple[str, str]:
    """The subtitle without the addresses written in it, and the item's address: its url, or the first one the
    subtitle had."""
    found = _URL_IN_TEXT.search(item.subtitle)
    subtitle = _URL_IN_TEXT.sub("", item.subtitle).strip()
    return subtitle, item.url or (found.group(1) if found else "")


def _problem(status: str, error: str) -> str:
    if status == "unavailable":
        return f"**{t('Not built:')}** {error or t('none of its plugins is installed and on.')}\n"
    stays = t("What it showed before stays.")
    failed = t("Couldn't build it:")
    return f"**{failed}** {error or t('no reason given.')} {stays}\n"


def updated(at: str, now: datetime) -> str:
    """When the page was last updated: "Updated 10:32" today, "Updated Wed 21 Oct 18:05" before; "" before the
    first refresh."""
    if not at:
        return ""
    when = datetime.fromisoformat(at).astimezone(now.tzinfo)
    return t("Updated {when}", when=when.strftime("%H:%M") if when.date() == now.date() else short_date(when))
