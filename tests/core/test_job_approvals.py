"""Scheduled runs that need approval ask on Telegram (a fake forwarder here) and wait; jobs that run
on new mail get the new messages; messages sent from outside a channel's chat reach it later."""

import asyncio
from datetime import UTC, datetime

import pytest

from assistant.core.config import settings
from assistant.core.integrations.imap import MailSummary
from assistant.core.jobs import store
from assistant.core.jobs.store import Job
from assistant.daemon.scheduler import Scheduler
from tests.conftest import collect


class _Forwarder:
    """Shows requests by recording them, and answers them with `decision` (or never, when None)."""

    def __init__(self, service, decision: dict | None) -> None:
        self._service = service
        self._decision = decision
        self.requests: list[tuple[str, dict]] = []

    async def forward(self, interrupt_id, title, request):
        self.requests.append((title, request))
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


async def test_an_unanswered_approval_is_rejected_after_the_wait(service, script, monkeypatch):
    monkeypatch.setattr(settings, "job_approval_minutes", 0.002)
    service.approvals.register("telegram", _Forwarder(service, None))
    script.call("bash", command="rm -rf build").reply("Couldn't clean up.")
    job = await _run(service, _due_job())
    assert job.runs[-1].status == "needs attention"
    tool_result = script.requests[-1][-1]
    assert "nobody answered on Telegram" in tool_result.content


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

    async def send(self, text: str) -> None:
        self.sent.append(text)


async def test_a_message_sent_from_elsewhere_reaches_the_channels_next_turn(service, script):
    service.outbox.register("telegram", _Sender())
    script.call("send_message", text="Time to stretch!").reply("Sent.")
    await collect(service.send(await service.session("owner", "cli"), "remind me on telegram"))
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


async def test_a_message_sent_from_the_channels_own_chat_isnt_repeated(service, script):
    service.outbox.register("telegram", _Sender())
    telegram = await service.session("owner", "telegram")
    script.call("send_message", text="Note").reply("Sent.")
    await collect(service.send(telegram, "send me a note"))
    script.reply("ok")
    await collect(service.send(telegram, "next"))
    assert not any("[You sent this on" in b.get("text", "") for b in script.requests[-1][-1].content)


@pytest.fixture(autouse=True)
def _short_timeouts(monkeypatch):
    monkeypatch.setattr(settings, "jobs_timeout_minutes", 1)
