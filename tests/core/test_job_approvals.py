"""Scheduled runs that need approval ask on Telegram (a fake forwarder here) and wait; jobs that run
on new mail get the new messages; messages sent from outside a channel's chat reach it later."""

import asyncio
from datetime import UTC, datetime

import pytest

from assistant.core.agent import Session
from assistant.core.config import settings
from assistant.core.integrations.email.imap import MailSummary
from assistant.core.jobs import active, store
from assistant.core.jobs.active import ActiveRun
from assistant.core.jobs.store import Job
from assistant.daemon.scheduler import Scheduler
from tests.conftest import collect


class _Forwarder:
    """Shows requests by recording them, and answers them with `decision` (or never, when None)."""

    def __init__(self, service, decision: dict | None) -> None:
        self._service = service
        self._decision = decision
        self.requests: list[tuple[str, dict]] = []
        self.ids: list[str] = []

    async def forward(self, interrupt_id, title, request):
        self.requests.append((title, request))
        self.ids.append(interrupt_id)
        if self._decision is not None:
            asyncio.get_running_loop().call_soon(self._service.approvals.answer, interrupt_id, self._decision)


async def _run(service, job: Job, mails: list[MailSummary] | None = None) -> Job:
    await store.save(service.store, job)
    scheduler = Scheduler(service)
    if mails is None:
        await scheduler.tick(datetime.now(UTC))
    else:
        await scheduler.run_for_mail(job, mails)
    for task in list(scheduler._running.values()):
        await task
    saved = await store.load(service.store, job.user_id, job.name)
    assert saved is not None
    return saved


def _due_job(task: str = "clean up") -> Job:
    return Job("cleanup", "owner", "0 9 * * *", "UTC", task, datetime.now(UTC).isoformat())


async def test_an_approval_goes_to_telegram_and_the_run_goes_on(service, script):
    forwarder = _Forwarder(service, {"approved": True})
    service.approvals.register("telegram", forwarder)
    script.call("bash", command="rm -rf build").reply("Cleaned up.")
    job = await _run(service, _due_job())
    assert forwarder.requests[0][0] == "The job cleanup" and forwarder.requests[0][1]["command"] == "rm -rf build"
    assert job.runs[-1].status == "ok" and job.runs[-1].summary == "Cleaned up."


async def test_an_approval_inside_a_delegated_task_goes_to_telegram_and_the_task_goes_on(service, script):
    forwarder = _Forwarder(service, {"approved": True})
    service.approvals.register("telegram", forwarder)
    script.call("delegate", task="clean the build folder")
    script.call("bash", command="rm -rf build").reply("Removed build.")
    script.reply("Cleaned up.")
    job = await _run(service, _due_job())
    assert forwarder.requests[0][1]["command"] == "rm -rf build"
    assert job.runs[-1].status == "ok" and job.runs[-1].summary == "Cleaned up."


async def test_with_no_channel_an_approval_inside_a_delegated_task_is_denied_and_noted(service, script):
    script.call("delegate", task="clean the build folder")
    script.call("bash", command="rm -rf build").reply("I wasn't allowed to remove it.")
    script.reply("Couldn't clean up.")
    job = await _run(service, _due_job())
    assert job.runs[-1].status == "needs attention"


async def test_an_unanswered_approval_is_rejected_after_the_wait(service, script, monkeypatch):
    monkeypatch.setattr(settings, "job_approval_minutes", 0.002)
    service.approvals.register("telegram", _Forwarder(service, None))
    script.call("bash", command="rm -rf build").reply("Couldn't clean up.")
    job = await _run(service, _due_job())
    assert job.runs[-1].status == "needs attention"
    tool_result = script.requests[-1][-1]
    assert "nobody answered on a chat channel" in tool_result.content


async def test_an_answer_after_the_run_went_on_is_refused(service):
    assert not service.approvals.answer("gone", {"approved": True})


async def test_a_mail_job_gets_the_new_messages(service, script):
    script.reply("Nothing urgent.")
    job = Job("bank-mail", "owner", "", "UTC", "Tell me if my bank wrote", "", on_new_mail=True)
    mail = MailSummary(42, "Bank <info@bank.com>", "Your statement", "2026-10-02T09:00:00+00:00", True)
    job = await _run(service, job, [mail])
    message = script.requests[-1][-1].content[-1]["text"]
    assert "Task: Tell me if my bank wrote" in message and "uid 42" in message and "Your statement" in message
    assert job.runs[-1].status == "ok" and job.state == "active"


async def test_mail_jobs_are_not_run_by_the_clock(service, script):
    job = Job("bank-mail", "owner", "", "UTC", "t", "", on_new_mail=True)
    job = await _run(service, job)
    assert job.runs == []


class _Sender:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> list[str]:
        self.sent.append(text)
        return [f"m{len(self.sent)}"]


async def test_a_message_sent_from_elsewhere_reaches_the_channels_next_turn(service, script):
    service.outbox.register("telegram", _Sender())
    script.call("send_message", text="Time to stretch!", channel="telegram").reply("Sent.")
    side = Session("owner", "cli", await service.new_thread("owner"))
    await collect(service.send(side, "remind me on telegram"))
    script.reply("You're welcome.")
    telegram = await service.session("owner", "telegram")
    await collect(service.send(telegram, "thanks"))
    blocks = script.requests[-1][-1].content
    assert blocks[1]["text"].startswith("[You sent this on telegram at ") and "Time to stretch!" in blocks[1]["text"]
    script.reply("Hi.")
    await collect(service.send(telegram, "hi"))
    assert not any("Time to stretch" in b.get("text", "") for b in script.requests[-1][-1].content)  # only once
    shown = await service.conversation_messages(telegram.thread_id)
    assert [m.text for m in shown if m.role == "user"] == ["thanks", "hi"]


async def test_a_message_sent_from_home_to_a_channel_on_home_isnt_repeated(service, script):
    service.outbox.register("telegram", _Sender())
    script.call("send_message", text="Time to stretch!", channel="telegram").reply("Sent.")
    await collect(service.send(await service.session("owner", "cli"), "remind me on telegram"))
    script.reply("You're welcome.")
    await collect(service.send(await service.session("owner", "telegram"), "thanks"))
    assert not any("Time to stretch" in b.get("text", "") for b in script.requests[-1][-1].content)


async def test_a_message_sent_from_the_channels_own_chat_isnt_repeated(service, script):
    service.outbox.register("telegram", _Sender())
    telegram = await service.session("owner", "telegram")
    script.call("send_message", text="Note", channel="telegram").reply("Sent.")
    await collect(service.send(telegram, "send me a note"))
    script.reply("ok")
    await collect(service.send(telegram, "next"))
    assert not any("[You sent this on" in b.get("text", "") for b in script.requests[-1][-1].content)


@pytest.fixture(autouse=True)
def _short_timeouts(monkeypatch):
    monkeypatch.setattr(settings, "jobs_timeout_minutes", 1)


class _SlowForwarder(_Forwarder):
    """Never answers; `asked` is set once a request is shown."""

    def __init__(self, service) -> None:
        super().__init__(service, None)
        self.asked = asyncio.Event()

    async def forward(self, interrupt_id, title, request):
        await super().forward(interrupt_id, title, request)
        self.asked.set()


async def _stop_while_asking(service, script) -> str:
    """Start a run that stops for approval, then stop the scheduler as the daemon does on restart.
    Returns the approval's interrupt id."""
    forwarder = _SlowForwarder(service)
    service.approvals.register("telegram", forwarder)
    script.call("bash", command="rm -rf build").reply("Cleaned up.")
    await store.save(service.store, _due_job())
    scheduler = Scheduler(service)
    await scheduler.tick(datetime.now(UTC))
    await forwarder.asked.wait()
    for task in list(scheduler._running.values()):
        task.cancel()
    await asyncio.gather(*scheduler._running.values(), return_exceptions=True)
    service.approvals.unregister("telegram")
    return forwarder.ids[0]


async def _resume(service) -> Job:
    scheduler = Scheduler(service)
    await scheduler.resume_interrupted()
    for task in list(scheduler._running.values()):
        await task
    saved = await store.load(service.store, "owner", "cleanup")
    assert saved is not None
    return saved


async def test_a_run_waiting_for_approval_asks_again_after_a_restart(service, script):
    interrupt_id = await _stop_while_asking(service, script)
    forwarder = _Forwarder(service, {"approved": True})
    service.approvals.register("telegram", forwarder)
    job = await _resume(service)
    # The same request, so the buttons sent before the restart still answer it.
    assert forwarder.ids == [interrupt_id] and forwarder.requests[0][1]["command"] == "rm -rf build"
    assert job.runs[-1].status == "ok" and job.runs[-1].summary == "Cleaned up."
    assert job.runs[-1].thread_id.startswith("job:cleanup:") and await active.all_runs(service.store) == []


async def test_after_a_restart_the_run_waits_for_telegram_to_connect(service, script):
    await _stop_while_asking(service, script)
    resumed = asyncio.create_task(_resume(service))
    await asyncio.sleep(0.05)
    assert not resumed.done()
    service.approvals.register("telegram", _Forwarder(service, {"approved": True}))
    job = await resumed
    assert job.runs[-1].status == "ok"


async def test_a_run_stopped_outside_an_approval_is_recorded_as_failed(service):
    await store.save(service.store, _due_job())
    run = ActiveRun("owner", "cleanup", "job:cleanup:2026-10-03T09:00:00", "2026-10-03T09:00:00+00:00")
    await active.start(service.store, run)
    job = await _resume(service)
    assert job.runs[-1].status == "failed" and job.runs[-1].summary == "the daemon stopped during the run"
    assert await active.all_runs(service.store) == []


async def test_a_finished_run_leaves_nothing_to_resume(service, script):
    script.reply("Done.")
    await _run(service, _due_job())
    assert await active.all_runs(service.store) == []
