"""Failures of MCP servers and skills as text, for the /mcp and /skills screens."""

from datetime import datetime

from assistant_terminal.i18n import t


def label(failing: bool) -> str:
    """Added to a list entry once it's failing enough to have been alerted."""
    return " · " + t("failing") if failing else ""


def failures_line(failures: int, failure: str, failed_at: str) -> str:
    """Markdown for the detail, or "" while it works."""
    if not failures:
        return ""
    when = datetime.fromisoformat(failed_at).astimezone().strftime("%Y-%m-%d %H:%M")
    times = t("Failed 1 time.") if failures == 1 else t("Failed {count} times in a row.", count=failures)
    return f"**{times}** " + t("Last, {when}: {failure}", when=when, failure=failure)
