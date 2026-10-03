"""Usage report as Markdown tables, shared by the /usage screen and the plain REPL."""

from assistant.core.agent import UsageReport
from assistant.core.usage.log import ToolUsage


def describe(report: UsageReport) -> str:
    return "\n\n".join(
        [
            f"## Usage, last {report.days} days",
            "### Tools",
            _table(report.tools, "Tool"),
            "### Skills",
            _table(report.skills, "Skill"),
        ]
    )


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
