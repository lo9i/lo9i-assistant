"""Usage report as Markdown tables, shared by the /usage screen and the plain REPL."""

from assistant.core.agent import TokenReport, UsageReport
from assistant.core.usage.log import TokenRow, ToolUsage
from assistant_terminal.i18n import decimal, t


def describe(report: UsageReport, tokens: TokenReport) -> str:
    return "\n\n".join(
        [
            "## " + t("Usage, last {days} days", days=report.days),
            *_tokens(tokens),
            "### " + t("Tool calls"),
            _table(report.tools, t("Tool")),
            "### " + t("Skill calls"),
            _table(report.skills, t("Skill")),
        ]
    )


def _tokens(report: TokenReport) -> list[str]:
    total = report.total
    title = "### " + t("Tokens")
    if not total.calls:
        return [title, t("(no model calls yet)")]
    summary = t(
        "{calls} model calls · {input} in ({cached} from the cache) · {output} out · {cost}",
        calls=total.calls,
        input=_count(total.input_tokens),
        cached=_count(total.cache_read_tokens),
        output=_count(total.output_tokens),
        cost=_cost(total.cost),
    )
    if report.estimated_calls:
        summary += " · " + t("{count} calls estimated (the provider reported no usage)", count=report.estimated_calls)
    sections = [
        (t("By model"), report.by_model, t("Model")),
        (t("By purpose"), report.by_purpose, t("Purpose")),
        (t("By conversation"), report.by_conversation, t("Conversation")),
        (t("By job"), report.by_job, t("Job")),
        (t("By skill in use"), report.by_skill, t("Skill")),
        (t("By channel"), report.by_channel, t("Channel")),
    ]
    lines = [title, summary]
    for heading, rows, label in sections:
        if rows:
            lines += [f"#### {heading}", _token_table(rows, label)]
    if report.by_tool:
        lines += ["#### " + t("Taken by tools (their results and calls)"), _tool_table(report.by_tool)]
    return lines


def _token_table(rows: list[TokenRow], label: str) -> str:
    columns = " | ".join([label, t("Calls"), t("In"), t("Cached"), t("Out"), t("Cost")])
    header = f"| {columns} |\n|---|---:|---:|---:|---:|---:|"
    lines = [
        f"| {r.label or r.name} | {r.calls} | {_count(r.input_tokens)} | {_count(r.cache_read_tokens)} "
        f"| {_count(r.output_tokens)} | {_cost(r.cost)} |"
        for r in rows
    ]
    return "\n".join([header, *lines])


def _tool_table(rows: list[TokenRow]) -> str:
    header = f"| {t('Tool')} | {t('Model calls')} | {t('In')} | {t('Out')} |\n|---|---:|---:|---:|"
    lines = [f"| {r.name} | {r.calls} | {_count(r.input_tokens)} | {_count(r.output_tokens)} |" for r in rows]
    return "\n".join([header, *lines])


def _count(tokens: int) -> str:
    if tokens >= 1_000_000:
        return f"{decimal(tokens / 1_000_000)}M"
    return f"{decimal(tokens / 1000)}k" if tokens >= 1000 else str(tokens)


def _cost(dollars: float | None) -> str:
    # No price for the model (core/usage/prices.py).
    return t("no price") if dollars is None else f"${dollars:.2f}"


def _table(rows: list[ToolUsage], label: str) -> str:
    if not rows:
        return t("(none yet)")
    columns = " | ".join([label, t("Calls"), t("Errors"), t("Denied"), t("Avg time"), t("Last used")])
    header = f"| {columns} |\n|---|---:|---:|---:|---:|---|"
    lines = [
        f"| {r.name} | {r.calls} | {r.errors} | {r.denied} | {_seconds(r.avg_ms)} | {_when(r.last_used)} |"
        for r in rows
    ]
    return "\n".join([header, *lines])


def _seconds(ms: int) -> str:
    return f"{ms} ms" if ms < 1000 else f"{decimal(ms / 1000)} s"


def _when(timestamp: str) -> str:
    return f"{timestamp[:16].replace('T', ' ')} UTC"
