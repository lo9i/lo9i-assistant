"""Background subagents as text, for /subagents and the line under the terminal app's title: each one's status, how
long it's been at it and what it's doing, and one's steps and answer."""

from datetime import UTC, datetime

from assistant.core.agent import BackgroundStep, BackgroundSubagent, Conversation
from assistant_terminal.conversations_text import listed_title
from assistant_terminal.i18n import t, translatable

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
    lines = [subagent.task, "", f"{status(subagent)} · {elapsed(subagent, now)}"]
    if subagent.step:
        lines.append(t("Now: {step}", step=subagent.step))
    for asked in subagent.waiting:
        lines.append(t("Asks: {what}", what=asked.request.get("command") or asked.request.get("reason") or ""))
    if steps:
        lines += ["", t("Steps:"), *(_step_line(s) for s in steps)]
    if subagent.result:
        lines += ["", t("Answer:") if subagent.status == "done" else t("What went wrong:"), subagent.result]
    return "\n".join(lines)


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


def _step_line(step: BackgroundStep) -> str:
    mark = "✓" if step.done else "…"
    first = next((v for v in step.args.values() if isinstance(v, str | int | float)), "")
    return f"  {mark} {_cut(f'{step.name} {first}'.strip(), _STEP)}"


def _first_line(text: str) -> str:
    return text.strip().split("\n", 1)[0]


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
