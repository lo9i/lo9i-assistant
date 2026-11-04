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
    if prompt == "where are uploads":
        return True, os.environ["LO9I_UPLOADS"]
    if prompt == "work a while":
        while not (repository / "release").exists():
            time.sleep(0.02)
    if prompt == "sleep":
        time.sleep(60)
    if prompt == "take messages":
        return _take_messages(folder)
    if prompt == "hold messages":
        return _hold_messages(folder)
    if prompt in ("leave messages", "leave messages and fail"):
        return _leave_messages(folder, repository, prompt == "leave messages")
    if prompt.startswith("work a while at context "):
        return _work_at_context(folder, repository, int(prompt.removeprefix("work a while at context ")))
    if prompt.startswith("fill context "):
        tokens = int(prompt.removeprefix("fill context "))
        (folder / "context.json").write_text(json.dumps({"tokens": tokens, "window": 200_000}))
    return True, f"Done in {repository}: {prompt}"


def _work_at_context(folder: Path, repository: Path, tokens: int) -> tuple[bool, str]:
    """Says how full its context is while it works, as a worker does after each step, then works until `release`."""
    (folder / "context.partial").write_text(json.dumps({"tokens": tokens, "window": 200_000}))
    os.replace(folder / "context.partial", folder / "context.json")
    while not (repository / "release").exists():
        time.sleep(0.02)
    return True, "Released."


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


def _hold_messages(folder: Path) -> tuple[bool, str]:
    """Passes on what the user sends while it works, as an agent that gets to it only once it's done with the step
    in progress, which never ends: each message's `user` step is marked `waiting`. A message starting with "take"
    it gets to at once (a `taken` step), "take all" with every one waiting before it, after saying so; one starting
    with "unread" it never passes on. It takes back a message the user withdraws while it waits."""
    signal.signal(signal.SIGUSR1, lambda *_: None)
    (folder / "inbox").mkdir()
    (folder / "withdraws").write_text("")
    _steps(folder, [json.dumps({"kind": "text", "text": "Working."})])
    seen: set[str] = set()
    waiting: list[str] = []
    while True:
        for path in sorted((folder / "inbox").glob("*.json")):
            message = json.loads(path.read_text())
            if path.stem in seen or message.get("text", "").startswith("unread"):
                continue
            seen.add(path.stem)
            _steps(folder, [json.dumps(step) for step in _held(path.stem, message, waiting)])
        time.sleep(0.02)


def _held(message_id: str, message: dict, waiting: list[str]) -> list[dict]:
    """The steps for a message of `_hold_messages`, and the ones still `waiting` after it."""
    if message["kind"] == "withdraw":
        if message["id"] not in waiting:
            return []
        waiting.remove(message["id"])
        return [{"kind": "withdrawn", "id": message["id"]}]
    text = message["text"]
    steps = [{"kind": "user", "text": text, "id": message_id, "waiting": True}]
    if text == "take all":
        steps += [{"kind": "text", "text": "Getting to them."}]
        steps += [{"kind": "taken", "id": taken} for taken in [*waiting, message_id]]
        waiting.clear()
    elif text.startswith("take"):
        steps += [{"kind": "taken", "id": message_id}]
    else:
        waiting.append(message_id)
    return steps


def _leave_messages(folder: Path, repository: Path, ok: bool) -> tuple[bool, str]:
    """Takes messages while it works, but ends once `release` is there without taking any."""
    signal.signal(signal.SIGUSR1, lambda *_: None)
    (folder / "inbox").mkdir()
    _steps(folder, [json.dumps({"kind": "text", "text": "Working."})])
    while not (repository / "release").exists():
        time.sleep(0.02)
    return (True, "Released.") if ok else (False, "it broke")


def _steps(folder: Path, lines: list[str]) -> None:
    with (folder / "progress.log").open("a") as log:
        log.writelines(line + "\n" for line in lines)


if __name__ == "__main__":
    main()
