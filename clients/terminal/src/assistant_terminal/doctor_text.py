"""The health check (core/doctor/) as text, for the /doctor screen: each cause, the overview of a report with its
starting context, as the web app's Health page shows them (lib/doctor.ts)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Cause, ContextPart, DoctorReport, KnownCause
from assistant.core.config import settings
from assistant_terminal.i18n import decimal, short_date, t, translatable

_CHANGES = {"new": translatable("New"), "growing": translatable("Growing")}


def cause_line(cause: Cause) -> str:
    """For the list: its change, what it is and how often."""
    change = f"[{t(_CHANGES[cause.change])}] " if cause.change else ""
    return f"{change}{cause.title} · {times(cause)}"


def known_line(known: KnownCause) -> str:
    return t("Known: {title}", title=known.title)


def times(cause: Cause) -> str:
    count = t("once") if cause.count == 1 else t("{count} times", count=cause.count)
    return (
        t("{count} ({before} the day before)", count=count, before=cause.before) if cause.change == "growing" else count
    )


def describe_cause(cause: Cause) -> str:
    kind = t("Log, {level}", level=cause.level.lower()) if cause.kind == "log" else t("Conversation")
    lines = [f"**{cause.title}**", "", "- " + t("Kind: {kind}", kind=kind)]
    if cause.where:
        lines.append("- " + t("Where: {where}", where=f"`{cause.where}`"))
    lines += [
        "- " + t("How often: {times}", times=times(cause)),
        "- " + t("First: {first}, last: {last}", first=_local(cause.first), last=_local(cause.last)),
    ]
    if cause.threads:
        lines.append("- " + t("In: {threads}", threads=", ".join(c.title or t("Untitled") for c in cause.threads)))
    if cause.example:
        lines += ["", "```", cause.example, "```"]
    return "\n".join(lines)


def describe_known(known: KnownCause) -> str:
    where = t(" at {where}", where=f"`{known.where}`") if known.where else ""
    marked = t("Marked as known noise {when}: left out of every check.", when=_local(known.at))
    return f"**{known.title}**{where}\n\n{marked} " + t("Not noise shows it again from the next check.")


def overview(report: DoctorReport | None) -> str:
    """When and what was checked, what's gone since the day before, and the starting context part by part."""
    if report is None:
        return t("Not checked yet. Check now checks today so far; the daemon checks each day once it ends.")
    lines = [_checked(report), ""]
    if not report.causes:
        lines += [t("Nothing wrong: no warnings or errors in the log, and no run failed."), ""]
    if report.gone:
        gone = "; ".join(c.title for c in report.gone)
        lines += [f"**{t('Gone since {day}:', day=report.compared_with)}** {gone}", ""]
    context = report.context
    share = round(100 * context.tokens / context.window) if context.window else 0
    flag = " — **" + t("large") + "**" if context.too_large else ""
    starting = t(
        "{tokens} of {window} tokens, {share}%",
        tokens=_tokens(context.tokens),
        window=_tokens(context.window),
        share=share,
    )
    lines += [
        f"**{t('Starting context:')}** {starting}{flag}",
        "",
        *(f"- {p.name}: {_part(p)}" for p in context.parts),
    ]
    return "\n".join(lines)


def _checked(report: DoctorReport) -> str:
    day = short_date(date.fromisoformat(report.day))
    span = t("{day}, the whole day", day=day) if report.whole_day else t("{day} so far", day=day)
    compared = (
        t("compared with {day}", day=report.compared_with)
        if report.compared_with
        else t("nothing earlier to compare with")
    )
    known = " " + t("{count} known cause(s) left out.", count=report.known) if report.known else ""
    return t("{span}, checked {when}; {compared}.", span=span, when=_local(report.at), compared=compared) + known


def _part(part: ContextPart) -> str:
    if part.before is None or part.before == part.tokens:
        return _tokens(part.tokens)
    change = part.tokens - part.before
    return f"{_tokens(part.tokens)} ({'+' if change > 0 else '-'}{_tokens(abs(change))})"


def _tokens(n: int) -> str:
    return f"{decimal(n / 1000)}k" if n >= 1000 else str(n)


def _local(timestamp: str) -> str:
    return short_date(datetime.fromisoformat(timestamp).astimezone(ZoneInfo(settings.timezone)))
