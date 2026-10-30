"""What changed since the day before: causes that are new or happen more than GROWING_TIMES as often, causes gone,
and how each part of the starting context grew. And what the doctor tells: the notification of a check, and the
alerts of its report."""

from assistant.core.doctor.model import Cause, DoctorAlert, DoctorReport, StartingContext
from assistant.core.i18n import Texts

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


def alerts(report: DoctorReport, t: Texts) -> list[DoctorAlert]:
    found = [_cause_alert(c, report, t) for c in report.causes if c.change and c.id not in report.dismissed]
    if report.context.too_large and CONTEXT_ALERT not in report.dismissed:
        found.append(_context_alert(report, t))
    return found


def notification_text(report: DoctorReport, t: Texts) -> str:
    logs = [c for c in report.causes if c.kind == "log"]
    talks = [c for c in report.causes if c.kind == "conversation"]
    lines = [
        _found(t("In the logs"), logs, [c for c in report.gone if c.kind == "log"], t),
        _found(t("In the conversations"), talks, [c for c in report.gone if c.kind == "conversation"], t),
        t("The starting context is {share} of the window.", share=context_share(report.context)),
    ]
    if report.known:
        lines.append(
            t("1 known cause left out.")
            if report.known == 1
            else t("{count} known causes left out.", count=report.known)
        )
    return " ".join(lines)


def named(context: StartingContext, t: Texts) -> StartingContext:
    """With its parts named in the language of `t`."""
    return context.model_copy(update={"parts": [p.model_copy(update={"name": t(p.name)}) for p in context.parts]})


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


def _found(where: str, causes: list[Cause], gone: list[Cause], t: Texts) -> str:
    if not causes:
        text = t("{where}: nothing wrong", where=where)
    else:
        new, growing = (sum(c.change == k for c in causes) for k in ("new", "growing"))
        changes = [
            *([t("{count} new", count=new)] if new else []),
            *([t("{count} growing", count=growing)] if growing else []),
        ]
        counted = t("1 cause") if len(causes) == 1 else t("{count} causes", count=len(causes))
        text = f"{where}: {counted}" + (f" ({', '.join(changes)})" if changes else "")
    return text + (t(", {count} gone.", count=len(gone)) if gone else ".")


def _cause_alert(cause: Cause, report: DoctorReport, t: Texts) -> DoctorAlert:
    times = t("once") if cause.count == 1 else t("{count} times", count=cause.count)
    if cause.change == "new":
        text = t("New since {before}: {times} on {day}.", before=report.compared_with, times=times, day=report.day)
    else:
        text = t(
            "{times} on {day}, {count} on {before}.",
            times=times,
            day=report.day,
            count=cause.before,
            before=report.compared_with,
        )
    place = t(" At {where}.", where=cause.where) if cause.where else ""
    return DoctorAlert(
        name=cause.id,
        kind=cause.change or "new",
        title=cause.title,
        text=text + place,
        count=cause.count,
        at=cause.last,
    )


def _context_alert(report: DoctorReport, t: Texts) -> DoctorAlert:
    context = report.context
    text = t(
        "A new conversation starts with {tokens} tokens, {share} of the {window} window.",
        tokens=_tokens(context.tokens),
        share=context_share(context),
        window=_tokens(context.window),
    )
    if grew := grew_most(named(context, t)):
        text += t(" Grew most since {before}: {grew}.", before=report.compared_with, grew=grew)
    return DoctorAlert(
        name=CONTEXT_ALERT,
        kind="context",
        title=t("The starting context is large"),
        text=text,
        count=0,
        at=report.at,
    )


def _tokens(n: int) -> str:
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)
