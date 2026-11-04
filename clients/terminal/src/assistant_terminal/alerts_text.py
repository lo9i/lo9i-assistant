"""Alerts as text, for the Alerts page (the web app's /alerts): MCP servers and skills that keep failing or need the
user to sign in again, and what the health check found new or growing, or the starting context too large."""

from datetime import datetime
from zoneinfo import ZoneInfo

from assistant.core.agent import Alert
from assistant.core.config import settings
from assistant_terminal.i18n import short_date, t, translatable

_KINDS = {"mcp": translatable("MCP server"), "skill": translatable("Skill"), "doctor": translatable("Health check")}


def alerted_at(alert: Alert) -> str:
    """When it happened last, in the user's timezone: its line in the list."""
    return short_date(datetime.fromisoformat(alert.at).astimezone(ZoneInfo(settings.timezone)))


def label(alert: Alert) -> str:
    """A health check's alert names a cause by its id: its title is what to show."""
    return alert.title or alert.name


def problem(alert: Alert) -> str:
    if alert.area == "doctor" and alert.kind == "context":
        return t("The context a new conversation starts with is large.")
    if alert.area == "doctor":
        count = t("once") if alert.failures == 1 else t("{count} times", count=alert.failures)
        change = t("New") if alert.kind == "new" else t("Growing")
        return f"{change}, {count}"
    if alert.kind == "signed_out":
        return t("Sign in again.")
    return t("Failed 1 time.") if alert.failures == 1 else t("Failed {count} times in a row.", count=alert.failures)


def describe(alert: Alert) -> str:
    """Markdown for the detail: what it is, what's wrong, when, and the error it last gave."""
    lines = [
        f"### {label(alert)}",
        "",
        "- " + t("Kind: {kind}", kind=t(_KINDS[alert.area])),
        "- " + t("Problem: {problem}", problem=problem(alert)),
        "- " + t("Last: {when}", when=alerted_at(alert)),
    ]
    if alert.error:
        lines += ["", "```", alert.error, "```"]
    return "\n".join(lines)
