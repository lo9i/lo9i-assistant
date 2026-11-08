"""Spending limits as text, shared by the /limits screen and the plain REPL: what each limit is, and reading what was
typed for one."""

from lo9i.core.agent import SpendingStatus
from lo9i.core.usage.limits import Kind
from lo9i_terminal.i18n import t, translatable

# Each limit by what the plain REPL's /limits calls it, with its label.
LIMITS: dict[Kind, tuple[str, str]] = {
    "job_run": ("job-run", translatable("Per run of a scheduled job")),
    "job_day": ("job-day", translatable("Per scheduled job, a day")),
    "conversation": ("conversation", translatable("Per conversation")),
    "day": ("day", translatable("Overall, a day")),
}


class NotAnAmountError(ValueError):
    pass


def describe(status: SpendingStatus) -> str:
    """Markdown: what the limits are for, each one, what was spent today and what counts."""
    rows = [f"- {t(label)}: {_amount(status.limits.of(kind))}" for kind, (_, label) in LIMITS.items()]
    return "\n\n".join(
        [
            "## " + t("Spending limits"),
            t(
                "What the model calls may spend, in US dollars as /usage prices them. A reply or a job's run that "
                "reaches a limit stops there and says which; at 80% your chat channels hear it once."
            ),
            "\n".join(rows),
            t("Spent today: {spent}", spent=f"US${status.spent_today:,.2f}"),
            hint(),
        ]
    )


def hint() -> str:
    return t(
        "Every model call counts, titles and memory included; a day starts at midnight where you are. Models with no "
        "known price (local ones, Copilot's subscription, any not priced in MODEL_PRICES) count as nothing."
    )


def amount_of(typed: str) -> float | None:
    """What was typed for a limit: an amount, or none when empty or off. Raises NotAnAmountError."""
    typed = typed.strip().removeprefix("$")
    if typed.lower() in ("", "off"):
        return None
    try:
        return float(typed)
    except ValueError:
        raise NotAnAmountError(t("Each limit is an amount, like 2.50, or empty for none.")) from None


def _amount(limit: float | None) -> str:
    return f"US${limit:,.2f}" if limit is not None else t("no limit")
