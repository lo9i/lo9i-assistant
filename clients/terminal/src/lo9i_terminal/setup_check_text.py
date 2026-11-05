"""The setup check (core/setup_check/) as text: plain lines for `lo9i doctor`, and Markdown for the Health tab's
Setup entry, as the web app's Setup card shows it (routes/doctor)."""

from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from lo9i.core.agent import SetupCheck, SetupReport
from lo9i.core.config import settings
from lo9i_terminal.i18n import short_date, t

_MARKS = {"ok": "✓", "warn": "!", "fail": "✗"}


def summary(checks: list[SetupCheck]) -> str:
    counts = Counter(c.status for c in checks)
    return t("{ok} ok, {warn} warning(s), {fail} failing.", ok=counts["ok"], warn=counts["warn"], fail=counts["fail"])


def lines(checks: list[SetupCheck]) -> str:
    """For a terminal: each part with its mark, its fix under it, then how many of each."""
    out: list[str] = []
    for check in checks:
        out.append(f"{_MARKS[check.status]} {check.title}: {check.detail}")
        if check.fix:
            out.append("    " + t("Fix: {fix}", fix=check.fix))
    return "\n".join([*out, "", summary(checks)])


def markdown(report: SetupReport | None) -> str:
    if report is None:
        return t(
            "Not checked yet. Check setup checks the daemon, the model's key, the plugins, email, chat channels, "
            "the web app, disk space and the lo9i command."
        )
    at = short_date(datetime.fromisoformat(report.at).astimezone(ZoneInfo(settings.timezone)))
    out = [t("Checked {when}. {summary}", when=at, summary=summary(report.checks)), ""]
    for check in report.checks:
        out.append(f"- {_MARKS[check.status]} **{check.title}**: {check.detail}")
        if check.fix:
            out.append("  " + t("Fix: {fix}", fix=check.fix))
    return "\n".join(out)
