import os
from pathlib import Path

import pytest

from lo9i.core.agent_tasks import pruning
from lo9i.core.disk import Places

NOW = 1_800_000_000.0
OLD = NOW - (pruning.KEEP_DAYS + 1) * 24 * 3600
RECENT = NOW - 24 * 3600


def _task(root: Path, task_id: str, *, ended: bool, changed: float) -> Path:
    folder = root / task_id
    (folder / "inbox").mkdir(parents=True)
    files = [folder / "task.json", folder / "progress.log", folder / "inbox" / "1.json"]
    if ended:
        files.append(folder / "result.json")
    for path in files:
        path.write_text("{}")
        os.utime(path, (changed, changed))
    for path in (folder / "inbox", folder):
        os.utime(path, (changed, changed))
    return folder


@pytest.fixture
def tasks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    root = tmp_path / "claude-code" / "tasks"
    found = {
        "ended": _task(root, "aaaa0001", ended=True, changed=OLD),
        "unfinished": _task(root, "aaaa0002", ended=False, changed=OLD),
        "recent": _task(root, "aaaa0003", ended=True, changed=RECENT),
        "running": _task(root, "aaaa0004", ended=True, changed=OLD),
    }
    # The worker of "running" wrote its result but hasn't exited yet.
    monkeypatch.setattr(pruning, "_running_commands", lambda: f"python worker.py {found['running']}\n")
    return found


def test_only_old_ended_tasks_are_pruned(tasks: dict[str, Path]) -> None:
    assert pruning.old_ended([tasks["ended"].parent], NOW) == [tasks["ended"]]


def test_a_recent_file_keeps_an_old_task(tasks: dict[str, Path]) -> None:
    os.utime(tasks["ended"] / "inbox" / "1.json", (RECENT, RECENT))
    assert pruning.old_ended([tasks["ended"].parent], NOW) == []


def test_prune_removes_them(tasks: dict[str, Path], tmp_path: Path) -> None:
    places = Places(tmp_path / "lo9i.db", (), tmp_path / "mcp", tmp_path, tmp_path, tmp_path / "up", tmp_path, ())
    cleaned = pruning.prune([tasks["ended"].parent], places, NOW)
    assert [Path(i.path) for i in cleaned.removed] == [tasks["ended"]] and cleaned.freed > 0
    assert not tasks["ended"].exists()
    assert all(tasks[name].exists() for name in ("unfinished", "recent", "running"))
