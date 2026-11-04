"""How long the briefing and a review may take, and what's recorded when one fails."""

from lo9i.core.i18n import message, said

# Longer fails, so a plugin that hangs can't hold the schedule.
SECONDS = 300


def reason(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return said("It took more than {minutes} minutes.", minutes=SECONDS // 60)
    text = message(error).strip() or type(error).__name__
    return text if len(text) <= 300 else text[:300] + "…"
