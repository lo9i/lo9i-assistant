"""How full the conversation's context is, as the web app's status bar shows it (ContextFuel.svelte): segments
that fill as it grows, in the accent colour until half full, yellow past half and red past three quarters, and
the percentage, or a dash while it isn't known. While the conversation is handed to an agent (/claude), the
agent's context as it last said, while it works too."""

from rich.text import Text

from assistant.core.agent import ConversationStats
from assistant_terminal.i18n import decimal, t

SEGMENTS = 16
_ACCENT, _YELLOW, _RED = "cyan", "#e5b931", "#e5534b"
# An en dash, as the web app shows in place of the percentage while the context isn't known.
UNKNOWN = "\u2013"


def known(stats: ConversationStats) -> bool:
    """No window, or no tokens yet (before the agent's first answer), isn't 0%."""
    return stats.context_limit > 0 and stats.context_tokens > 0


def fuel(stats: ConversationStats) -> Text:
    """The segments and the percentage; empty segments and a dash while the context isn't known."""
    ratio = min(1.0, stats.context_tokens / stats.context_limit) if known(stats) else 0.0
    filled = round(ratio * SEGMENTS)
    color = _ACCENT if ratio <= 0.5 else _YELLOW if ratio <= 0.75 else _RED
    who = f"{stats.context_agent} " if stats.context_agent else ""
    figure = f" {round(ratio * 100)}%" if known(stats) else f" {UNKNOWN}"
    return Text.assemble((who, "dim"), ("▰" * filled, color), ("▱" * (SEGMENTS - filled), "dim"), (figure, color))


def detail(stats: ConversationStats) -> str:
    """What the figures are, as the web app's hover says."""
    if not known(stats):
        return t("Not known until its first answer.")
    figures = t("{used} / {limit} tokens", used=compact(stats.context_tokens), limit=compact(stats.context_limit))
    if stats.context_agent:
        return t("{agent}'s context: {figures}, updated as it works.", agent=stats.context_agent, figures=figures)
    return t("Context: {figures}. Older messages are summarized when it's full.", figures=figures)


def compact(tokens: int) -> str:
    """1.2k, 45k, 1.3M."""
    if tokens >= 1_000_000:
        return f"{decimal(tokens / 1_000_000)}M"
    if tokens >= 10_000:
        return f"{round(tokens / 1000)}k"
    return f"{decimal(tokens / 1000)}k" if tokens >= 1000 else str(tokens)
