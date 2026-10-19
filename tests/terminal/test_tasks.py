from datetime import UTC, datetime

from assistant.core.agent import RunningTask
from assistant_terminal.tasks_text import task_line
from tests.terminal.conftest import wait_for

_NOW = datetime(2026, 10, 9, 10, 18, tzinfo=UTC)


def _task(thread_id: str, steps: list[str]) -> RunningTask:
    return RunningTask("a1", "Claude Code", thread_id, "fix the tests", "2026-10-09T10:00:00+00:00", steps)


def test_a_task_line_says_how_long_where_and_its_latest_step():
    assert (
        task_line(_task("t1", ["Read: README.md", "Bash: pytest"]), "t1", _NOW)
        == "Claude Code working 18m: Bash: pytest"
    )
    assert task_line(_task("t2", []), "t1", _NOW) == "Claude Code working 18m in another conversation"


async def test_running_tasks_show_under_the_title_as_they_go(app, client):
    async with app.run_test() as pilot:
        thread_id = app._live.session.thread_id
        client.tasks.tasks = [_task(thread_id, ["Bash: pytest"])]
        await client.bus.put(("agent_task_progress", {"task_id": "a1"}))
        await wait_for(pilot, lambda: "Claude Code working" in app.sub_title and "Bash: pytest" in app.sub_title)
        client.tasks.tasks = []
        await client.bus.put(("agent_task_reports", {}))
        await wait_for(pilot, lambda: app.sub_title == "inbox")
