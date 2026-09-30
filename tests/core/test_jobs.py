"""Job tools and the scheduler: due runs, missed runs, unattended results, edits during runs."""

from datetime import UTC, datetime, timedelta

from assistant.core.jobs import store
from assistant.core.jobs.schedule import next_runs
from assistant.core.jobs.store import Job
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


async def test_denied_action_marks_the_run_as_needing_attention(service, script):
    now = await _job_due(service, script, minutes_ago=1)
    script.call("bash", command="rm -rf build").reply("couldn't clean up")
    job = await _run_tick(service, now)
    assert job.runs[-1].status == "needs attention"


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
    assert "(paused)" in outputs[0] and "daily-news (paused)" in outputs[1] and outputs[2] == "Deleted daily-news."


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
    assert "either" in both
    neither = await _schedule(service, script, name="x", task="t")
    assert "either" in neither
