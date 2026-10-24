"""How full the conversation's context is, as the web app's status bar shows it (ContextFuel.svelte): segments
that fill as it grows, in the accent colour until half full, yellow past half and red past three quarters, and
the percentage. While the conversation is handed to an agent (/claude), the agent's context, as of its last
answer."""

from rich.text import Text

from assistant.core.agent import ConversationStats

SEGMENTS = 16
_ACCENT, _YELLOW, _RED = "cyan", "#e5b931", "#e5534b"


def fuel(stats: ConversationStats) -> Text:
    """The segments and the percentage; empty while the context isn't known."""
    if stats.context_limit <= 0 or stats.context_tokens <= 0:
        return Text()
    ratio = min(1.0, stats.context_tokens / stats.context_limit)
    filled = round(ratio * SEGMENTS)
    color = _ACCENT if ratio <= 0.5 else _YELLOW if ratio <= 0.75 else _RED
    who = f"{stats.context_agent} " if stats.context_agent else ""
    return Text.assemble(
        (who, "dim"), ("▰" * filled, color), ("▱" * (SEGMENTS - filled), "dim"), (f" {round(ratio * 100)}%", color)
    )


def detail(stats: ConversationStats) -> str:
    """What the figures are, as the web app's hover says."""
    figures = f"{compact(stats.context_tokens)} / {compact(stats.context_limit)} tokens"
    if stats.context_agent:
        return f"{stats.context_agent}'s context: {figures}, as of its last answer."
    return f"Context: {figures}. Older messages are summarized when it's full."


def compact(tokens: int) -> str:
    """1.2k, 45k, 1.3M."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 10_000:
        return f"{round(tokens / 1000)}k"
    return f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens)
