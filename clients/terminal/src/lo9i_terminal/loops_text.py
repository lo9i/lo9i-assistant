"""Open loops as text, for Home's Open loops card in /home: each loop's line under the card, and the whole of the one
picked."""

from datetime import datetime
from zoneinfo import ZoneInfo

from lo9i.core.agent import OpenLoop
from lo9i.core.config import settings
from lo9i_terminal.i18n import short_date, t, translatable

_SOURCES = {
    "conversation": translatable("A conversation"),
    "review": translatable("A review"),
    "briefing": translatable("The briefing"),
    "assistant": translatable("The assistant"),
}


def local(at: str) -> str:
    return short_date(datetime.fromisoformat(at).astimezone(ZoneInfo(settings.timezone)))


def loop_line(loop: OpenLoop) -> str:
    due = f" · {loop.due}" if loop.due else ""
    return f"{loop.text}{due}"


def describe_loop(loop: OpenLoop) -> str:
    lines = [f"## {loop.text}", ""]
    lines += [f"- {t('Kind')}: {loop.kind}"] if loop.kind else []
    lines += [f"- {t('Due')}: {loop.due}"] if loop.due else []
    lines += [f"- {t('Reminder')}: {local(loop.remind_at)}"] if loop.remind_at else []
    lines += [f"- {t('From')}: {t(_SOURCES[loop.source])}", f"- {t('Since')}: {local(loop.created_at)}"]
    return "\n".join(lines)
