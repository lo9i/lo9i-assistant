"""The briefing, the reviews and the open loops as text, for the /briefing screen."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import OpenLoop, ProactivePage
from assistant.core.config import settings
from assistant_terminal.i18n import short_date, t, translatable

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


def overview(page: ProactivePage) -> str:
    return "\n\n".join([_briefing(page), _review(page)])


def _briefing(page: ProactivePage) -> str:
    briefing = page.briefing
    heading = f"## {t('Latest briefing')}"
    if briefing is None:
        return f"{heading}\n\n{t('No briefing yet: the first one comes at {time}.', time=page.settings.briefing_time)}"
    if briefing.status == "failed":
        state = t("Failed: {error}", error=briefing.error)
    elif briefing.status == "nothing":
        state = t("Nothing worth telling that day.")
    elif briefing.channels:
        state = t("Sent to {channels}", channels=", ".join(briefing.channels))
    else:
        state = t("Only in Notifications: no chat channel was connected.")
    return "\n\n".join(filter(None, [heading, f"{local(briefing.at)} · {state}", briefing.text]))


def _review(page: ProactivePage) -> str:
    heading = f"## {t('Latest review')}"
    review = page.reviews[0] if page.reviews else None
    if review is None:
        return f"{heading}\n\n{t('No review yet.')}"
    kind = t("Weekly review") if review.kind == "weekly" else t("Nightly review")
    counts = t("{added} loops added, {closed} closed", added=review.added, closed=review.closed)
    parts = [heading, f"{kind} · {local(review.at)} · {counts}"]
    parts += [t("Failed: {error}", error=review.error)] if review.error else []
    parts += [review.summary] if review.summary else []
    parts += ["\n".join(f"- {s.text} ({s.kind})" for s in review.suggestions)] if review.suggestions else []
    return "\n\n".join(parts)
