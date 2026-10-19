"""A coding agent's worker for the tests, following docs/agent-plugins.md: it does what the task says."""

import json
import os
import sys
import time
from pathlib import Path

_WORKING = [
    {"kind": "thinking", "text": "The test expects a list."},
    {"kind": "text", "text": "Running the tests."},
    {"kind": "tool", "tool": "Bash", "detail": "pytest -q", "id": "t1"},
    {"kind": "result", "tool": "Bash", "text": "1 failed", "id": "t1"},
    {"kind": "text", "text": "Fixed it."},
    {"kind": "text", "text": "All green."},
]


def main() -> None:
    folder = Path(sys.argv[-1])
    os.setsid()
    (folder / "pid").write_text(str(os.getpid()))
    task = json.loads((folder / "task.json").read_text())
    ok, text = _work(folder, task)
    (folder / "result.partial").write_text(json.dumps({"ok": ok, "text": text, "finished_at": "now"}))
    os.replace(folder / "result.partial", folder / "result.json")


def _work(folder: Path, task: dict) -> tuple[bool, str]:
    prompt, repository = task["prompt"], Path(task["repository"])
    if prompt == "work out loud":
        _steps(folder, [json.dumps(step) for step in _WORKING])
        return True, "All green."
    if prompt == "think, then answer":
        _steps(folder, [json.dumps({"kind": "thinking", "text": "Easy one."})])
        return True, "Four."
    if prompt == "show your steps":
        _steps(folder, ["Read: README.md", "Ran: pytest"])
    if prompt == "break":
        return False, "the agent gave up"
    if prompt == "session":
        return True, f"Session {task['session']}"
    if prompt == "work a while":
        while not (repository / "release").exists():
            time.sleep(0.02)
    if prompt == "sleep":
        time.sleep(60)
    return True, f"Done in {repository}: {prompt}"


def _steps(folder: Path, lines: list[str]) -> None:
    with (folder / "progress.log").open("a") as log:
        log.writelines(line + "\n" for line in lines)


if __name__ == "__main__":
    main()
