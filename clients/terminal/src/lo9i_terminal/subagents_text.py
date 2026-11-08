"""Background subagents as text, for /subagents and the line under the terminal app's title: each one's status, how
long it's been at it and what it's doing, and one's status line (its context and model calls, as the web app's), its
steps with when each was asked for, and its answer."""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from lo9i.core.agent import BackgroundStep, BackgroundSubagent, Conversation
from lo9i.core.config import settings
from lo9i_terminal.approval_text import approval_title, call_of
from lo9i_terminal.context_text import UNKNOWN, compact
from lo9i_terminal.conversations_text import listed_title
from lo9i_terminal.i18n import t, translatable

_STATUS = {
    "running": translatable("working"),
    "waiting": translatable("waiting for your answer"),
    "done": translatable("finished"),
    "failed": translatable("failed"),
    "stopped": translatable("stopped"),
}
_MARK = {"running": "…", "waiting": "?", "done": "✓", "failed": "✗", "stopped": "■"}
_TASK, _STEP, _CONVERSATION = 48, 60, 32


def status(subagent: BackgroundSubagent) -> str:
    return t(_STATUS.get(subagent.status, subagent.status))


def elapsed(subagent: BackgroundSubagent, now: datetime | None = None) -> str:
    """How long it's been at it, or was until it ended: 45s, 3m, 1h 5m."""
    end = datetime.fromisoformat(subagent.ended_at) if subagent.ended_at else (now or datetime.now(UTC))
    seconds = max(0, int((end - datetime.fromisoformat(subagent.started_at)).total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    return f"{minutes}m" if minutes < 60 else f"{minutes // 60}h {minutes % 60}m"


def subagent_line(subagent: BackgroundSubagent, now: datetime | None = None, conversation: str = "") -> str:
    """Its status, how long, and its task's start, after the conversation it works for when given."""
    task = _cut(_first_line(subagent.task), _TASK)
    working_for = f"{_cut(conversation, _CONVERSATION)}: " if conversation else ""
    return f"{_MARK.get(subagent.status, '·')} {status(subagent)} · {elapsed(subagent, now)} · {working_for}{task}"


def conversation_titles(subagents: list[BackgroundSubagent], conversations: list[Conversation]) -> dict[str, str]:
    """The title of the conversation each works for, by its id; untitled for one not listed."""
    listed = {c.thread_id: listed_title(c) for c in conversations}
    return {s.thread_id: listed.get(s.thread_id) or t("Untitled") for s in subagents}


def subagent_detail(subagent: BackgroundSubagent, steps: list[BackgroundStep], now: datetime | None = None) -> str:
    """Its task, status, what it's doing, its steps and how it ended, as plain text."""
    lines = [subagent.task, "", f"{status(subagent)} · {elapsed(subagent, now)}", context_line(subagent)]
    if subagent.step:
        lines.append(t("Now: {step}", step=subagent.step))
    for asked in subagent.waiting:
        lines.append(t("Asks: {what}", what=_asks(asked.request)))
    if steps:
        lines += ["", t("Steps:"), *(_step_line(s, now) for s in steps)]
    if subagent.result:
        lines += ["", t("Answer:") if subagent.status == "done" else t("What went wrong:"), subagent.result]
    return "\n".join(lines)


def context_line(subagent: BackgroundSubagent) -> str:
    """How full its context is and how many model calls it made, as the web app's status line under it says."""
    known = subagent.context_limit > 0 and subagent.context_tokens > 0
    used, limit = subagent.context_tokens, subagent.context_limit
    percent = f"{round(min(1.0, used / limit) * 100)}%" if known else UNKNOWN
    figures = t("{used} / {limit} tokens", used=compact(used), limit=compact(limit)) if known else ""
    calls = t("Model calls: {count}", count=subagent.model_calls)
    return " · ".join(filter(None, [t("Context: {percent}", percent=percent), figures, calls]))


def _asks(request: dict[str, Any]) -> str:
    """An MCP tool's call by its tool and server, as its approval says; anything else by its command."""
    if call_of(request):
        return approval_title(request)
    return str(request.get("command") or request.get("reason") or "")


def running_line(subagents: list[BackgroundSubagent]) -> str:
    """For the line under the title: how many work in this conversation, and how many wait for an answer."""
    working = [s for s in subagents if s.status in ("running", "waiting")]
    if not working:
        return ""
    waiting = sum(s.status == "waiting" for s in working)
    line = (
        t("a subagent working (/subagents)")
        if len(working) == 1
        else t("{count} subagents working (/subagents)", count=len(working))
    )
    return line + (t(", {count} waiting for you", count=waiting) if waiting else "")


def _step_line(step: BackgroundStep, now: datetime | None) -> str:
    mark = "✓" if step.done else "…"
    first = next((v for v in step.args.values() if isinstance(v, str | int | float)), "")
    return f"  {mark} {_at(step.at, now)}{_cut(f'{step.name} {first}'.strip(), _STEP)}"


def _at(at: str, now: datetime | None) -> str:
    """When its model asked for it, as the conversation's calls show it: the time, with the day when not today."""
    if not at:
        return ""
    zone = ZoneInfo(settings.timezone)
    started, today = datetime.fromisoformat(at).astimezone(zone), (now or datetime.now(UTC)).astimezone(zone).date()
    return started.strftime("%H:%M " if started.date() == today else "%d %b %H:%M ")


def _first_line(text: str) -> str:
    return text.strip().split("\n", 1)[0]


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
