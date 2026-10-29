"""A coding agent's running task as one line, for the line under the terminal app's title."""

from datetime import UTC, datetime

from assistant.core.agent import RunningTask
from assistant_terminal.i18n import t

_STEP = 60


def task_line(task: RunningTask, thread_id: str, now: datetime | None = None) -> str:
    """Who's working, for how long, where when it's another conversation, and its latest step."""
    started = datetime.fromisoformat(task.started_at)
    minutes = int(((now or datetime.now(UTC)) - started).total_seconds() // 60)
    elsewhere = task.thread_id and task.thread_id != thread_id
    values = {"agent": task.agent, "minutes": minutes}
    line = (
        t("{agent} working {minutes}m in another conversation", **values)
        if elsewhere
        else t("{agent} working {minutes}m", **values)
    )
    if task.steps:
        step = task.steps[-1]
        line += f": {step if len(step) <= _STEP else step[: _STEP - 1] + '…'}"
    return line
