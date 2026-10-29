"""The Copilot allowance, watched without the model: GitHub's report read into quotas, Home's Copilot card built
from the last check, and an alert on WhatsApp once below 20% and once out, each once per period."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from langgraph.store.memory import InMemoryStore

from assistant.core import language
from assistant.core.copilot_quota import records
from assistant.core.copilot_quota.alerts import SentAlerts, after, due
from assistant.core.copilot_quota.quota import CopilotQuota, QuotaCheckError, fetch, parse
from assistant.core.copilot_quota.section import CopilotSection, items
from assistant.core.copilot_quota.watch import CHECK_HOURS, CopilotWatch
from assistant.core.home import sections
from assistant.core.home.model import HomeSection
from assistant.core.i18n import texts
from assistant.core.llm.choice import ModelChoice
from assistant.core.outbox import Outbox

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)
ES = texts("es")
COPILOT = ModelChoice("copilot", "claude-opus-5.5", "gpt-5-mini", {"api_key": "gh-token"})


def _snapshot(**fields: Any) -> dict[str, Any]:
    return {
        "unlimited": False,
        "percent_remaining": 100.0,
        "remaining": 300,
        "entitlement": 300,
        "overage_permitted": False,
        "credits_used": 0,
        "quota_id": "premium_interactions",
        **fields,
    }


def _report(premium: dict[str, Any], chat: dict[str, Any] | None = None, reset: str = "2026-11-01") -> dict[str, Any]:
    chat = chat or _snapshot(unlimited=True, remaining=0, entitlement=0)
    return {
        "copilot_plan": "business",
        "quota_reset_date": reset,
        "quota_snapshots": {"premium_interactions": premium, "chat": chat, "completions": _snapshot(unlimited=True)},
    }


def _quota(percent: float, reset: str = "2026-11-01") -> CopilotQuota:
    return parse(_report(_snapshot(percent_remaining=percent, remaining=3 * percent), reset=reset))


def test_githubs_report_reads_as_the_plan_and_its_quotas():
    quota = parse(_report(_snapshot(unlimited=True, remaining=0, entitlement=0, credits_used=2361)))
    assert (quota.plan, quota.reset_date) == ("business", "2026-11-01")
    assert quota.premium is not None and quota.premium.unlimited and quota.premium.credits_used == 2361
    assert quota.lowest() is None  # unlimited everywhere: nothing to run out of


def test_a_report_without_quotas_isnt_read():
    with pytest.raises(QuotaCheckError):
        parse({"copilot_plan": "business"})
    with pytest.raises(QuotaCheckError):
        parse(_report(_snapshot(percent_remaining=None)))


def test_the_quota_with_least_left_counts():
    quota = parse(_report(_snapshot(percent_remaining=60), chat=_snapshot(percent_remaining=12)))
    assert quota.lowest() == quota.chat


async def test_a_refused_token_is_a_check_error():
    transport = httpx.MockTransport(lambda request: httpx.Response(401))
    with pytest.raises(QuotaCheckError, match="rejected"):
        await fetch("gh-wrong", transport)


def test_no_alert_while_unlimited_or_above_twenty_percent():
    assert due(ES, parse(_report(_snapshot(unlimited=True, remaining=0))), SentAlerts()) is None
    assert due(ES, _quota(20), SentAlerts()) is None


def test_low_then_out_each_once_per_period():
    low = due(ES, _quota(15.4), SentAlerts())
    assert low is not None and low.text == "Copilot: queda 15% del cupo mensual (se renueva el 1/11)."
    sent = after(_quota(15.4), SentAlerts(), low)
    assert due(ES, _quota(5), sent) is None
    out = due(ES, _quota(0), sent)
    assert out is not None and out.text == "Copilot: se agotó el cupo mensual (se renueva el 1/11)."
    assert due(ES, _quota(0), after(_quota(0), sent, out)) is None


def test_alerts_are_in_the_language_chosen():
    low = due(texts("en"), _quota(15.4), SentAlerts())
    assert low is not None and low.text == "Copilot: 15% of this month's allowance left (renews on 11/1)."


def test_running_out_at_once_is_told_and_low_isnt_after_it():
    out = due(ES, _quota(0), SentAlerts())
    assert out is not None and out.level == "out"
    assert due(ES, _quota(10), after(_quota(0), SentAlerts(), out)) is None


def test_a_new_period_alerts_again():
    low = due(ES, _quota(10), SentAlerts())
    assert low is not None
    sent = after(_quota(10), SentAlerts(), low)
    assert due(ES, _quota(10, reset="2026-12-01"), sent) is not None


def test_the_card_shows_the_plan_whats_left_credits_and_reset():
    limited = items(texts("en"), parse(_report(_snapshot(percent_remaining=15, remaining=45, credits_used=2361))))
    assert [(i.title, i.subtitle, i.date) for i in limited] == [
        ("Plan: business", "", ""),
        ("Premium requests: 15% left (45 of 300)", "2,361 credits used", ""),
        ("Resets", "", "2026-11-01"),
    ]
    unlimited = items(texts("en"), parse(_report(_snapshot(unlimited=True, credits_used=2361))))
    assert unlimited[1].title == "Premium requests: Unlimited"
    spanish = items(ES, parse(_report(_snapshot(percent_remaining=15, remaining=45, credits_used=2361))))
    assert (spanish[1].title, spanish[1].subtitle) == (
        "Solicitudes premium: queda 15% (45 de 300)",
        "2.361 créditos usados",
    )


class _WhatsApp:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> list[str]:
        self.sent.append(text)
        return [str(len(self.sent))]


class _GitHub:
    def __init__(self, report: dict[str, Any]) -> None:
        self.report: dict[str, Any] | None = report
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        assert request.headers["Authorization"] == "token gh-token"
        return httpx.Response(200, json=self.report) if self.report else httpx.Response(503)


def _watch(store: InMemoryStore, outbox: Outbox, github: _GitHub, model: ModelChoice = COPILOT) -> CopilotWatch:
    async def _checked() -> None:
        pass

    return CopilotWatch(store, outbox, lambda: model, _checked, "owner", httpx.MockTransport(github.handler))


async def test_the_watch_checks_at_start_and_every_few_hours_and_alerts_once():
    store, outbox, whatsapp = InMemoryStore(), Outbox(), _WhatsApp()
    await language.save(store, "es")
    outbox.register("whatsapp", whatsapp)
    github = _GitHub(_report(_snapshot(percent_remaining=15, remaining=45)))
    watch = _watch(store, outbox, github)
    await watch.tick(NOW)
    await watch.tick(NOW + timedelta(minutes=1))
    assert github.calls == 1
    await watch.tick(NOW + timedelta(hours=CHECK_HOURS))
    assert github.calls == 2
    assert whatsapp.sent == ["Copilot: queda 15% del cupo mensual (se renueva el 1/11)."]


async def test_an_alert_waits_for_whatsapp_to_connect():
    store, outbox, whatsapp = InMemoryStore(), Outbox(), _WhatsApp()
    await language.save(store, "es")
    watch = _watch(store, outbox, _GitHub(_report(_snapshot(percent_remaining=0, remaining=0))))
    await watch.tick(NOW)
    outbox.register("whatsapp", whatsapp)
    await watch.tick(NOW + timedelta(minutes=1))
    assert whatsapp.sent == ["Copilot: se agotó el cupo mensual (se renueva el 1/11)."]


async def test_with_another_provider_nothing_is_checked():
    github = _GitHub(_report(_snapshot()))
    await _watch(InMemoryStore(), Outbox(), github, ModelChoice("openai", "gpt-5", "gpt-5-mini")).tick(NOW)
    assert github.calls == 0


async def test_a_failed_check_is_logged_at_info_and_keeps_the_last_allowance(caplog):
    store, github = InMemoryStore(), _GitHub(_report(_snapshot(percent_remaining=50, remaining=150)))
    watch = _watch(store, Outbox(), github)
    await watch.tick(NOW)
    github.report = None
    with caplog.at_level(logging.INFO):
        await watch.tick(NOW + timedelta(hours=CHECK_HOURS))
    assert [r.levelno for r in caplog.records if "allowance" in r.getMessage()] == [logging.INFO]
    check = await records.last(store)
    assert check is not None and check.quota is not None and "503" in check.error
    content = await CopilotSection(store, lambda: COPILOT).build()
    assert content.items and content.note.startswith("Couldn't check it again")


async def test_the_copilot_card_joins_sections_saved_before_it_and_stays_removed():
    store = InMemoryStore()
    mine = HomeSection(id="news", title="News", prompt="Today's news.")
    await store.aput(sections.namespace("owner"), "sections", {"sections": [mine.model_dump()]})
    assert [s.id for s in await sections.load(store, "owner")] == ["news", sections.COPILOT]
    await sections.save(store, "owner", [mine])
    assert [s.id for s in await sections.load(store, "owner")] == ["news"]
