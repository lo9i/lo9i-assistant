"""A coding agent's worker for the tests, following docs/agent-plugins.md: it does what the task says."""

import json
import os
import signal
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

# A call that starts a subagent of the agent's own, whose steps carry the call's id as `within`.
_DELEGATING = [
    {"kind": "tool", "tool": "Task", "detail": "find the bug", "id": "t1"},
    {"kind": "thinking", "text": "Looking for parse.", "within": "t1"},
    {"kind": "tool", "tool": "Grep", "detail": "def parse", "id": "s1", "within": "t1"},
    {"kind": "result", "tool": "Grep", "text": "parse.py:3", "id": "s1", "within": "t1"},
    {"kind": "result", "tool": "Task", "text": "It's in parse.py", "id": "t1"},
    {"kind": "text", "text": "Found it in parse.py."},
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
    if prompt == "delegate":
        _steps(folder, [json.dumps(step) for step in _DELEGATING])
        return True, "Found it in parse.py."
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
    if prompt == "take messages":
        return _take_messages(folder)
    return True, f"Done in {repository}: {prompt}"


def _take_messages(folder: Path) -> tuple[bool, str]:
    """Takes what the user sends while it works, from its inbox: an interrupt is a note, a message a step of
    its own, and "that's all" ends it, leaving any message after it."""
    signal.signal(signal.SIGUSR1, lambda *_: None)
    (folder / "inbox").mkdir()
    _steps(folder, [json.dumps({"kind": "text", "text": "Working."})])
    taken: set[str] = set()
    while True:
        for path in sorted((folder / "inbox").glob("*.json")):
            if path.stem in taken:
                continue
            taken.add(path.stem)
            message = json.loads(path.read_text())
            if message["kind"] == "interrupt":
                _steps(folder, [json.dumps({"kind": "note", "text": "Interrupted"})])
                continue
            _steps(folder, [json.dumps({"kind": "user", "text": message["text"], "id": path.stem})])
            if message["text"] == "that's all":
                return True, f"Took {len(taken)} messages."
        time.sleep(0.02)


def _steps(folder: Path, lines: list[str]) -> None:
    with (folder / "progress.log").open("a") as log:
        log.writelines(line + "\n" for line in lines)


if __name__ == "__main__":
    main()
