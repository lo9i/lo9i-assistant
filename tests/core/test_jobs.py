"""Job tools and the scheduler: due runs, missed runs, unattended results, edits during runs."""

from datetime import UTC, datetime, timedelta

from assistant.core import notifications
from assistant.core.jobs import store
from assistant.core.jobs.schedule import next_runs
from assistant.core.jobs.store import Job, RunRecord
from assistant.daemon.scheduler import Scheduler
from tests.conftest import collect


async def _schedule(service, script, **args):
    script.call("schedule_job", **args).reply("scheduled")
    events = await collect(service.send(await service.session("owner", "cli"), "schedule it"))
    return events[1].output


async def test_schedule_job_validates_and_describes_the_next_runs(service, script):
    out = await _schedule(service, script, name="daily-news", schedule="0 9 * * *", task="Run the skill news-digest")
    assert out.startswith("Scheduled daily-news: next runs:") and "09:00" in out
    bad = await _schedule(service, script, name="x", schedule="every day", task="t")
    assert "Not a valid cron schedule" in bad


def test_next_run_is_computed_in_the_jobs_time_zone():
    after = datetime(2026, 9, 30, 11, 0, tzinfo=UTC)  # 08:00 in Buenos Aires
    run = next_runs("0 9 * * *", "America/Argentina/Buenos_Aires", after)[0]
    assert run.astimezone(UTC) == datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


async def _job_due(service, script, minutes_ago: float, task="say hi"):
    await _schedule(service, script, name="daily-news", schedule="0 9 * * *", task=task)
    job = await store.load(service.store, "owner", "daily-news")
    assert job is not None
    now = datetime.now(UTC)
    job.next_run_at = (now - timedelta(minutes=minutes_ago)).isoformat()
    await store.save(service.store, job)
    return now


async def _run_tick(service, now) -> Job:
    scheduler = Scheduler(service)
    await scheduler.tick(now)
    for task in list(scheduler._running.values()):
        await task
    job = await store.load(service.store, "owner", "daily-news")
    assert job is not None
    return job


async def test_due_job_runs_unattended_and_records_the_result(service, script):
    now = await _job_due(service, script, minutes_ago=1)
    script.reply("Here is today's summary.")
    job = await _run_tick(service, now)
    assert job.runs[-1].status == "ok" and "today's summary" in job.runs[-1].summary
    assert job.runs[-1].thread_id.startswith("job:daily-news:")
    assert datetime.fromisoformat(job.next_run_at) > now
    [told] = await notifications.recent(service.store, "owner")
    assert (told.kind, told.title, told.ok, told.thread_id) == ("job", "Job daily-news", True, "")
    assert "today's summary" in told.text


async def test_denied_action_marks_the_run_as_needing_attention(service, script):
    now = await _job_due(service, script, minutes_ago=1)
    script.call("bash", command="rm -rf build").reply("couldn't clean up")
    job = await _run_tick(service, now)
    assert job.runs[-1].status == "needs attention"
    [told] = await notifications.recent(service.store, "owner")
    assert not told.ok and told.text.startswith("Needs attention: ")


async def test_run_missed_beyond_the_grace_window_is_recorded_not_run(service, script):
    now = await _job_due(service, script, minutes_ago=7 * 60)
    job = await _run_tick(service, now)
    assert job.runs[-1].status == "missed" and datetime.fromisoformat(job.next_run_at) > now


async def test_list_update_and_delete(service, script):
    await _schedule(service, script, name="daily-news", schedule="0 9 * * *", task="t")
    script.call("update_job", name="daily-news", enabled=False).call("list_jobs").call(
        "delete_job", name="daily-news"
    ).reply("ok")
    events = await collect(service.send(await service.session("owner", "cli"), "manage"))
    outputs = [e.output for e in events if hasattr(e, "output")]
    assert "(paused)" in outputs[0] and "Paused, won't run until resumed (1):\n- daily-news" in outputs[1]
    assert outputs[2] == "Deleted daily-news."


async def _list(service, script, **args) -> str:
    script.call("list_jobs", **args).reply("ok")
    events = await collect(service.send(await service.session("owner", "cli"), "which jobs?"))
    return events[1].output


async def test_jobs_are_listed_as_active_paused_or_done(service, script):
    await _schedule(service, script, name="daily-news", schedule="0 9 * * *", task="news")
    await _schedule(service, script, name="weekly-report", schedule="0 9 * * 1", task="report")
    paused = await store.load(service.store, "owner", "weekly-report")
    assert paused is not None
    paused.enabled = False
    await store.save(service.store, paused)
    ran = RunRecord(datetime.now(UTC).isoformat(), "ok", "stretched")
    done = Job("stretch", "owner", "", "UTC", "say stretch", ran.at, enabled=False, runs=[ran], one_time=True)
    await store.save(service.store, done)
    assert [j.state for j in (paused, done)] == ["paused", "done"]

    listed = await _list(service, script)
    active, paused_part, done_part = listed.split("\n\n")
    assert active.startswith("Active, will run (1):\n- daily-news:") and "next run" in active
    assert paused_part.startswith("Paused, won't run until resumed (1):\n- weekly-report:")
    assert "next run" not in paused_part  # a paused job has no next run
    assert done_part.startswith("Done, one-time jobs that already ran (1):\n- stretch: ran once, finished")
    assert "stretched" in done_part
    only_active = await _list(service, script, state="active")
    assert "daily-news" in only_active and "weekly-report" not in only_active and "stretch" not in only_active
    assert await _list(service, script, state="done") != "No done jobs."


async def test_one_time_job_runs_once_then_turns_off(service, script):
    soon = (datetime.now(UTC) + timedelta(minutes=1)).isoformat(timespec="minutes")
    out = await _schedule(service, script, name="stretch", at=soon, task="say stretch")
    assert out.startswith("Scheduled stretch: runs once at")
    job = await store.load(service.store, "owner", "stretch")
    assert job is not None and job.one_time and job.schedule == ""
    due = datetime.fromisoformat(job.next_run_at) + timedelta(seconds=5)
    script.reply("Stretch!")
    scheduler = Scheduler(service)
    await scheduler.tick(due)
    for task in list(scheduler._running.values()):
        await task
    await scheduler.tick(due + timedelta(minutes=5))
    job = await store.load(service.store, "owner", "stretch")
    assert job is not None and not job.enabled and [r.status for r in job.runs] == ["ok"]


async def test_schedule_needs_exactly_one_future_timing(service, script):
    past = await _schedule(service, script, name="x", at="2020-01-01T09:00", task="t")
    assert "already passed" in past
    both = await _schedule(service, script, name="x", schedule="0 9 * * *", at="2030-01-01T09:00", task="t")
    assert "one of" in both
    neither = await _schedule(service, script, name="x", task="t")
    assert "one of" in neither
