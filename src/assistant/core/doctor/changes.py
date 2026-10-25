"""What changed since the day before: causes that are new or happen more than GROWING_TIMES as often, causes gone,
and how each part of the starting context grew. And what the doctor tells: the notification of a check, and the
alerts of its report."""

from assistant.core.doctor.model import Cause, DoctorAlert, DoctorReport, StartingContext

GROWING_TIMES = 2
# What the alert of the starting context is named, beside the causes' ids.
CONTEXT_ALERT = "context"
_GREW_SHOWN = 3


def compared(causes: list[Cause], previous: DoctorReport | None) -> tuple[list[Cause], list[Cause]]:
    """The causes with their change since `previous`, new and growing first, and the causes gone. Nothing is new
    without an earlier report: the first check would alert on everything."""
    if previous is None:
        return causes, []
    before = {c.id: c for c in previous.causes}
    changed = [_against(c, before.get(c.id)) for c in causes]
    ids = {c.id for c in causes}
    gone = [c for c in previous.causes if c.id not in ids]
    return sorted(changed, key=lambda c: not c.change), gone


def compared_context(context: StartingContext, previous: DoctorReport | None) -> StartingContext:
    if previous is None:
        return context
    before = {p.name: p.tokens for p in previous.context.parts}
    parts = [p.model_copy(update={"before": before.get(p.name)}) for p in context.parts]
    return context.model_copy(update={"parts": parts})


def alerts(report: DoctorReport) -> list[DoctorAlert]:
    found = [_cause_alert(c, report) for c in report.causes if c.change and c.id not in report.dismissed]
    if report.context.too_large and CONTEXT_ALERT not in report.dismissed:
        found.append(_context_alert(report))
    return found


def notification_text(report: DoctorReport) -> str:
    logs = [c for c in report.causes if c.kind == "log"]
    talks = [c for c in report.causes if c.kind == "conversation"]
    lines = [
        _found("In the logs", logs, [c for c in report.gone if c.kind == "log"]),
        _found("In the conversations", talks, [c for c in report.gone if c.kind == "conversation"]),
        f"The starting context is {context_share(report.context)} of the window.",
    ]
    if report.known:
        lines.append(f"{_count(report.known, 'known cause')} left out.")
    return " ".join(lines)


def context_share(context: StartingContext) -> str:
    return f"{round(100 * context.tokens / context.window)}%" if context.window else "?"


def grew_most(context: StartingContext) -> str:
    """Like "Saved facts +3.1k, Skills +200"; "" when nothing grew or there's nothing to compare with."""
    grown = [(p.name, p.tokens - p.before) for p in context.parts if p.before is not None and p.tokens > p.before]
    grown.sort(key=lambda g: g[1], reverse=True)
    return ", ".join(f"{name} +{_tokens(growth)}" for name, growth in grown[:_GREW_SHOWN])


def _against(cause: Cause, before: Cause | None) -> Cause:
    if before is None:
        return cause.model_copy(update={"change": "new"})
    growing = cause.count > before.count * GROWING_TIMES
    return cause.model_copy(update={"change": "growing" if growing else "", "before": before.count})


def _found(where: str, causes: list[Cause], gone: list[Cause]) -> str:
    if not causes:
        text = f"{where}: nothing wrong"
    else:
        counts = [(sum(c.change == k for c in causes), k) for k in ("new", "growing")]
        changes = [f"{n} {k}" for n, k in counts if n]
        text = f"{where}: {_count(len(causes), 'cause')}" + (f" ({', '.join(changes)})" if changes else "")
    return text + (f", {len(gone)} gone." if gone else ".")


def _cause_alert(cause: Cause, report: DoctorReport) -> DoctorAlert:
    times = _count(cause.count, "time")
    if cause.change == "new":
        text = f"New since {report.compared_with}: {times} on {report.day}."
    else:
        text = f"{times} on {report.day}, {cause.before} on {report.compared_with}."
    place = f" At {cause.where}." if cause.where else ""
    return DoctorAlert(
        name=cause.id,
        kind=cause.change or "new",
        title=cause.title,
        text=text + place,
        count=cause.count,
        at=cause.last,
    )


def _context_alert(report: DoctorReport) -> DoctorAlert:
    context = report.context
    text = (
        f"A new conversation starts with {_tokens(context.tokens)} tokens, {context_share(context)} of the "
        f"{_tokens(context.window)} window."
    )
    if grew := grew_most(context):
        text += f" Grew most since {report.compared_with}: {grew}."
    return DoctorAlert(
        name=CONTEXT_ALERT, kind="context", title="The starting context is large", text=text, count=0, at=report.at
    )


def _count(n: int, what: str) -> str:
    return f"{n} {what}" + ("" if n == 1 else "s")


def _tokens(n: int) -> str:
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)
