"""A task's records, one folder per task under the plugin's data folder:

- task.json: what was asked. The daemon writes it once, when the task starts.
- pid: the worker's process id. The worker writes it when it starts.
- progress.log: what the agent is doing, one JSON step per line (docs/agent-plugins.md), with the words
  of its text and thinking as they're written. The worker appends to it.
- result.json: how it ended. The worker writes it last.
- stopped: the user stopped it. The daemon writes it.
- conversation: the conversation handed to the agent that the task answers in (AgentTasks.converse). The
  daemon writes it before the worker starts.
- inbox/: what the user sends the task while it works. The worker makes the folder once it takes them;
  the daemon writes each message in it as a file of its own, then wakes the worker (workers.wake).
- worker.log: the worker's output, for finding out why one failed.

Every file has one writer, so the daemon and the worker never race on one. A task's state comes from
which of them exist and whether its worker is still alive. These run blocking file calls: async code
calls them in a thread.
"""

import json
import os
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from assistant.core.agent_tasks.steps import parse, streamed

Status = Literal["running", "done", "failed", "stopped"]

_TASK = "task.json"
_PID = "pid"
_PROGRESS = "progress.log"
_RESULT = "result.json"
_STOPPED = "stopped"
_CONVERSATION = "conversation"
_INBOX = "inbox"
# How long a task may go without its worker's pid before it counts as a worker that never started.
_START_SECONDS = 60


class TaskNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class Task:
    id: str
    repository: str
    prompt: str
    # The agent's session: a follow-up continues its earlier task's session.
    session: str
    # The task this one follows up on; "" for a new session.
    follow_up_of: str
    started_at: str


@dataclass(frozen=True)
class Outcome:
    ok: bool
    # The agent's final answer, or what went wrong.
    text: str
    finished_at: str = ""
    cost_usd: float | None = None


@dataclass(frozen=True)
class TaskState:
    task: Task
    status: Status
    # Set once it's done or failed.
    outcome: Outcome | None
    # The last steps in progress.log, as written, without the words streamed before their whole block.
    progress: list[str]


class TaskStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def create(self, repository: str, prompt: str, session: str = "", follow_up_of: str = "") -> Task:
        task = Task(
            id=uuid.uuid4().hex[:8],
            repository=repository,
            prompt=prompt,
            session=session or str(uuid.uuid4()),
            follow_up_of=follow_up_of,
            started_at=_now(),
        )
        folder = self.folder(task.id)
        folder.mkdir(parents=True)
        _write_json(folder / _TASK, asdict(task))
        return task

    def folder(self, task_id: str) -> Path:
        return self.root / task_id

    def has(self, task_id: str) -> bool:
        return task_id.isalnum() and (self.folder(task_id) / _TASK).is_file()

    def get(self, task_id: str) -> Task:
        if not self.has(task_id):
            raise TaskNotFoundError(f"No task {task_id}.")
        return Task(**json.loads((self.folder(task_id) / _TASK).read_text()))

    def recent(self, limit: int = 20) -> list[Task]:
        """Newest first, by when their record was written: `started_at` is only to the second."""
        records = sorted(self.root.glob(f"*/{_TASK}"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        return [self.get(record.parent.name) for record in records[:limit]]

    def state(self, task_id: str, progress_lines: int = 30) -> TaskState:
        task = self.get(task_id)
        folder = self.folder(task_id)
        outcome, alive = self._ended(task)
        steps = [line for line in _tail(folder / _PROGRESS, None) if not streamed(line)]
        progress = steps[-progress_lines:] if progress_lines else []
        return TaskState(task, self._status(task, outcome, alive), outcome, progress)

    def pid(self, task_id: str) -> int | None:
        path = self.folder(task_id) / _PID
        return int(path.read_text()) if path.is_file() else None

    def mark_stopped(self, task_id: str) -> None:
        (self.folder(task_id) / _STOPPED).write_text(_now())

    def mark_conversation(self, task_id: str, thread_id: str) -> None:
        (self.folder(task_id) / _CONVERSATION).write_text(thread_id)

    def conversation(self, task_id: str) -> str:
        """The conversation the task answers in; "" for one it doesn't (start_task)."""
        path = self.folder(task_id) / _CONVERSATION
        return path.read_text() if path.is_file() else ""

    def takes_messages(self, task_id: str) -> bool:
        """Its worker takes messages while it works: it made the inbox."""
        return (self.folder(task_id) / _INBOX).is_dir()

    def add_message(self, task_id: str, message: dict[str, Any]) -> None:
        """A message for the worker (docs/agent-plugins.md), named so it sorts after the ones before."""
        _write_json(self.folder(task_id) / _INBOX / f"{time.time_ns()}-{uuid.uuid4().hex[:6]}.json", message)

    def message(self, task_id: str, message_id: str) -> dict[str, Any] | None:
        """The message sent to it under that id (a `user` step's), or None when there's none."""
        path = self.folder(task_id) / _INBOX / f"{message_id}.json"
        if Path(message_id).name != message_id or not path.is_file():
            return None
        return json.loads(path.read_text())

    def untaken(self, task_id: str) -> list[dict[str, Any]]:
        """The messages its worker ended without taking, oldest first."""
        folder = self.folder(task_id)
        taken = {step.get("id") for step in map(parse, _tail(folder / _PROGRESS, None)) if step.get("kind") == "user"}
        sent = [path for path in sorted((folder / _INBOX).glob("*.json")) if path.stem not in taken]
        messages = [json.loads(path.read_text()) for path in sent]
        return [message for message in messages if message.get("kind") == "message"]

    def progress_after(self, task_id: str, seen: int) -> list[str]:
        """The task's progress lines after the first `seen`, for following it as it goes."""
        return _tail(self.folder(task_id) / _PROGRESS, None)[seen:]

    def _ended(self, task: Task) -> tuple[Outcome | None, bool]:
        """Its result, and whether its worker still runs. A worker writes its result just before it exits, so
        the result is read again after the worker is found gone: the first read can come just before it was
        written, and a task that ended well would read as lost."""
        path = self.folder(task.id) / _RESULT
        if (outcome := _read_outcome(path)) is not None:
            return outcome, False
        if self._alive(task):
            return None, True
        return _read_outcome(path), False

    def _status(self, task: Task, outcome: Outcome | None, alive: bool) -> Status:
        if (self.folder(task.id) / _STOPPED).exists():
            return "stopped"
        if outcome is not None:
            return "done" if outcome.ok else "failed"
        return "running" if alive else "failed"

    def _alive(self, task: Task) -> bool:
        """Its worker is running: the process with its pid is the one started for this task's folder,
        not another that got the same pid after a restart. Without a pid yet, it's starting, for a while."""
        folder = self.folder(task.id)
        pid_file = folder / _PID
        if not pid_file.is_file():
            age = datetime.now(UTC) - datetime.fromisoformat(task.started_at)
            return age.total_seconds() < _START_SECONDS
        return str(folder) in _command_of(int(pid_file.read_text()))


def lost(state: TaskState) -> bool:
    """It failed without a result: its worker was killed (a restart, out of memory) before it finished."""
    return state.status == "failed" and state.outcome is None


def _command_of(pid: int) -> str:
    found = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=False)
    return found.stdout


def _read_outcome(path: Path) -> Outcome | None:
    return Outcome(**json.loads(path.read_text())) if path.is_file() else None


def _tail(path: Path, lines: int | None) -> list[str]:
    """The last `lines` lines, or all of them for None."""
    if not path.is_file():
        return []
    every = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return every if lines is None else every[-lines:]


def _write_json(path: Path, data: dict) -> None:
    """Written whole and then renamed, so a reader never sees half of it."""
    partial = path.with_suffix(".partial")
    partial.write_text(json.dumps(data, indent=2))
    os.replace(partial, path)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
