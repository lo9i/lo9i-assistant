"""Usage report as Markdown tables, shared by the /usage screen and the plain REPL."""

from assistant.core.agent import TokenReport, UsageReport
from assistant.core.usage.log import TokenRow, ToolUsage


def describe(report: UsageReport, tokens: TokenReport) -> str:
    return "\n\n".join(
        [
            f"## Usage, last {report.days} days",
            *_tokens(tokens),
            "### Tool calls",
            _table(report.tools, "Tool"),
            "### Skill calls",
            _table(report.skills, "Skill"),
        ]
    )


def _tokens(report: TokenReport) -> list[str]:
    total = report.total
    if not total.calls:
        return ["### Tokens", "(no model calls yet)"]
    cached = f"({_count(total.cache_read_tokens)} from the cache)"
    summary = (
        f"{total.calls} model calls · {_count(total.input_tokens)} in {cached}"
        f" · {_count(total.output_tokens)} out · {_cost(total.cost)}"
    )
    if report.estimated_calls:
        summary += f" · {report.estimated_calls} calls estimated (the provider reported no usage)"
    sections = [
        ("By model", report.by_model, "Model"),
        ("By purpose", report.by_purpose, "Purpose"),
        ("By conversation", report.by_conversation, "Conversation"),
        ("By job", report.by_job, "Job"),
        ("By skill in use", report.by_skill, "Skill"),
        ("By channel", report.by_channel, "Channel"),
    ]
    lines = ["### Tokens", summary]
    for title, rows, label in sections:
        if rows:
            lines += [f"#### {title}", _token_table(rows, label)]
    if report.by_tool:
        lines += ["#### Taken by tools (their results and calls)", _tool_table(report.by_tool)]
    return lines


def _token_table(rows: list[TokenRow], label: str) -> str:
    header = f"| {label} | Calls | In | Cached | Out | Cost |\n|---|---:|---:|---:|---:|---:|"
    lines = [
        f"| {r.label or r.name} | {r.calls} | {_count(r.input_tokens)} | {_count(r.cache_read_tokens)} "
        f"| {_count(r.output_tokens)} | {_cost(r.cost)} |"
        for r in rows
    ]
    return "\n".join([header, *lines])


def _tool_table(rows: list[TokenRow]) -> str:
    header = "| Tool | Model calls | In | Out |\n|---|---:|---:|---:|"
    lines = [f"| {r.name} | {r.calls} | {_count(r.input_tokens)} | {_count(r.output_tokens)} |" for r in rows]
    return "\n".join([header, *lines])


def _count(tokens: int) -> str:
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    return f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens)


def _cost(dollars: float | None) -> str:
    # No price for the model (core/usage/prices.py).
    return "no price" if dollars is None else f"${dollars:.2f}"


def _table(rows: list[ToolUsage], label: str) -> str:
    if not rows:
        return "(none yet)"
    header = f"| {label} | Calls | Errors | Denied | Avg time | Last used |\n|---|---:|---:|---:|---:|---|"
    lines = [
        f"| {r.name} | {r.calls} | {r.errors} | {r.denied} | {_seconds(r.avg_ms)} | {_when(r.last_used)} |"
        for r in rows
    ]
    return "\n".join([header, *lines])


def _seconds(ms: int) -> str:
    return f"{ms} ms" if ms < 1000 else f"{ms / 1000:.1f} s"


def _when(timestamp: str) -> str:
    return f"{timestamp[:16].replace('T', ' ')} UTC"
