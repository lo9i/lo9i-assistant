"""A restart or stop of the daemon that's pending, as the rest of lo9i sees it (core/ending.py): kept in a file
readable without the daemon, gone once it's taken back and when the daemon starts."""

import json
from datetime import datetime
from pathlib import Path

from lo9i.core.ending import AskedEnding, EndingState


def test_a_pending_restart_is_written_with_who_asked_when_and_the_runs_it_waits_for(tmp_path: Path):
    path = tmp_path / "restart-pending.json"
    running = ["owner:fix"]
    state = EndingState(path, lambda: list(running))
    assert state.current() is None and not path.exists()
    state.asked("restart", "web (device Mac)")
    written = json.loads(path.read_text())
    assert (written["ending"], written["asked_by"], written["waiting_for"]) == ("restart", "web (device Mac)", running)
    datetime.fromisoformat(written["asked_at"])
    # Read live: a run that ended isn't waited for any more.
    running.clear()
    assert state.current() == AskedEnding("restart", "web (device Mac)", written["asked_at"], [])


def test_a_stop_asked_for_while_a_restart_waits_replaces_it_and_keeps_when_it_was_first_asked(tmp_path: Path):
    state = EndingState(tmp_path / "restart-pending.json", lambda: [])
    state.asked("restart", "web")
    first = state.current()
    state.asked("stop", "terminal")
    assert first is not None and state.current() == AskedEnding("stop", "terminal", first.asked_at, [])


def test_taking_it_back_or_starting_again_deletes_the_file(tmp_path: Path):
    path = tmp_path / "restart-pending.json"
    state = EndingState(path, lambda: [])
    state.asked("restart", "web")
    state.taken_back()
    assert state.current() is None and not path.exists()
    path.write_text("{}")  # left by a daemon that ended
    EndingState(path, lambda: []).clear_left_over()
    assert not path.exists()
