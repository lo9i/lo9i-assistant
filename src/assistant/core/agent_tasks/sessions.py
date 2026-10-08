"""Which task each handed-over conversation is at in each folder, so its next message continues that
task's session. A small file per conversation and folder, next to the plugin's tasks. These block: async
code calls them in a thread."""

import contextlib
import hashlib
import json
from pathlib import Path

from assistant.core.agent_tasks.records import Task, TaskNotFoundError, TaskStore


class Sessions:
    def __init__(self, root: Path) -> None:
        self._root = root

    def last(self, conversation: str, folder: str, store: TaskStore) -> Task | None:
        path = self._path(conversation, folder)
        if not path.is_file():
            return None
        with contextlib.suppress(TaskNotFoundError):
            return store.get(json.loads(path.read_text())["task"])
        return None

    def record(self, conversation: str, folder: str, task: Task) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._path(conversation, folder).write_text(json.dumps({"task": task.id}))

    def _path(self, conversation: str, folder: str) -> Path:
        key = hashlib.sha256(f"{conversation}\n{folder}".encode()).hexdigest()[:24]
        return self._root / f"{key}.json"
