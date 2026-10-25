"""The health check (core/doctor/) as text, for the /doctor screen: each cause, the overview of a report with its
starting context, as the web app's Health page shows them (lib/doctor.ts)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Cause, ContextPart, DoctorReport, KnownCause
from assistant.core.config import settings

_CHANGES = {"new": "New", "growing": "Growing"}


def cause_line(cause: Cause) -> str:
    """For the list: its change, what it is and how often."""
    change = f"[{_CHANGES[cause.change]}] " if cause.change else ""
    return f"{change}{cause.title} · {times(cause)}"


def known_line(known: KnownCause) -> str:
    return f"Known: {known.title}"


def times(cause: Cause) -> str:
    count = "once" if cause.count == 1 else f"{cause.count} times"
    return f"{count} ({cause.before} the day before)" if cause.change == "growing" else count


def describe_cause(cause: Cause) -> str:
    kind = f"Log, {cause.level.lower()}" if cause.kind == "log" else "Conversation"
    lines = [f"**{cause.title}**", "", f"- Kind: {kind}"]
    if cause.where:
        lines.append(f"- Where: `{cause.where}`")
    lines += [
        f"- How often: {times(cause)}",
        f"- First: {_local(cause.first)}, last: {_local(cause.last)}",
    ]
    if cause.threads:
        lines.append(f"- In: {', '.join(t.title or 'Untitled' for t in cause.threads)}")
    if cause.example:
        lines += ["", "```", cause.example, "```"]
    return "\n".join(lines)


def describe_known(known: KnownCause) -> str:
    where = f" at `{known.where}`" if known.where else ""
    marked = f"Marked as known noise {_local(known.at)}: left out of every check."
    return f"**{known.title}**{where}\n\n{marked} Not noise shows it again from the next check."


def overview(report: DoctorReport | None) -> str:
    """When and what was checked, what's gone since the day before, and the starting context part by part."""
    if report is None:
        return "Not checked yet. Check now checks today so far; the daemon checks each day once it ends."
    lines = [_checked(report), ""]
    if not report.causes:
        lines += ["Nothing wrong: no warnings or errors in the log, and no run failed.", ""]
    if report.gone:
        lines += [f"**Gone since {report.compared_with}:** " + "; ".join(c.title for c in report.gone), ""]
    context = report.context
    share = round(100 * context.tokens / context.window) if context.window else 0
    flag = " — **large**" if context.too_large else ""
    lines += [
        f"**Starting context:** {_tokens(context.tokens)} of {_tokens(context.window)} tokens, {share}%{flag}",
        "",
        *(f"- {p.name}: {_part(p)}" for p in context.parts),
    ]
    return "\n".join(lines)


def _checked(report: DoctorReport) -> str:
    day = date.fromisoformat(report.day).strftime("%a %d %b")
    span = f"{day}, the whole day" if report.whole_day else f"{day} so far"
    compared = f"compared with {report.compared_with}" if report.compared_with else "nothing earlier to compare with"
    known = f" {report.known} known cause(s) left out." if report.known else ""
    return f"{span}, checked {_local(report.at)}; {compared}.{known}"


def _part(part: ContextPart) -> str:
    if part.before is None or part.before == part.tokens:
        return _tokens(part.tokens)
    change = part.tokens - part.before
    return f"{_tokens(part.tokens)} ({'+' if change > 0 else '-'}{_tokens(abs(change))})"


def _tokens(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _local(timestamp: str) -> str:
    return f"{datetime.fromisoformat(timestamp).astimezone(ZoneInfo(settings.timezone)):%a %d %b %H:%M}"
