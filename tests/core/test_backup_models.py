"""Backup models: a reply whose model fails on the provider's side is written by the first backup that answers, saying
so; a failure that isn't the provider's never falls back."""

import httpx
from langchain_core.exceptions import ContextOverflowError

from lo9i.core.events import Error, TextDelta
from lo9i.core.llm import backups
from lo9i.core.llm.backups import Backup
from lo9i.core.llm.errors import provider_failed
from tests.conftest import collect


class _StatusError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status_code = status


class APIConnectionError(Exception):
    """Named as the SDKs name theirs."""


def test_provider_failures_are_told_from_the_requests_own():
    assert all(provider_failed(_StatusError(s)) for s in (429, 402, 500, 503, 529))
    assert provider_failed(APIConnectionError("reset"))
    assert provider_failed(httpx.ConnectTimeout("slow"))
    assert not any(provider_failed(_StatusError(s)) for s in (400, 401, 404, 413))
    assert not provider_failed(ContextOverflowError("too long"))
    assert not provider_failed(ValueError("bad"))


async def _with_backups(service, script, monkeypatch, *names: str) -> None:
    monkeypatch.setattr(backups, "build_llm", lambda choice, model: script.model())
    saved = [Backup(backups.new_id(), "anthropic", name) for name in names]
    await backups.save(service._storage.store, service.secrets, saved)


async def test_a_backup_answers_when_the_main_model_is_rate_limited(service, script, monkeypatch):
    await _with_backups(service, script, monkeypatch, "claude-sonnet-5-5")
    script.refuse(_StatusError(429)).reply("Hello from the backup.")
    session = await service.session("owner", "cli")
    events = await collect(service.send(session, "hi"))
    said = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert "the backup model claude-sonnet-5-5 answered" in said
    assert not any(isinstance(e, Error) for e in events)
    shown = await service.conversation_messages(session.thread_id)
    assert "claude-sonnet-5-5 answered" in shown[-1].text
    assert "Hello from the backup." in shown[-1].text


async def test_backups_are_tried_in_order_and_the_note_comes_once_per_run(service, script, monkeypatch):
    await _with_backups(service, script, monkeypatch, "first-backup", "second-backup")
    script.refuse(_StatusError(503)).refuse(_StatusError(529)).call("list_jobs")
    script.refuse(_StatusError(503)).reply("Done.")
    session = await service.session("owner", "cli")
    events = await collect(service.send(session, "hi"))
    said = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert said.count("second-backup answered") == 1
    assert not any(isinstance(e, Error) for e in events)


async def test_a_failure_that_isnt_the_providers_doesnt_fall_back(service, script, monkeypatch):
    await _with_backups(service, script, monkeypatch, "claude-sonnet-5-5")
    script.refuse(_StatusError(400)).reply("never")
    session = await service.session("owner", "cli")
    events = await collect(service.send(session, "hi"))
    assert any(isinstance(e, Error) for e in events)
    assert len(script.requests) == 1


async def test_without_backups_the_run_fails_as_before(service, script):
    script.refuse(_StatusError(429))
    session = await service.session("owner", "cli")
    events = await collect(service.send(session, "hi"))
    assert any(isinstance(e, Error) for e in events)


async def test_backups_keep_their_order_and_secrets(service):
    store, box = service._storage.store, service.secrets
    await backups.save(
        store,
        box,
        [Backup("a", "anthropic", "one"), Backup("b", "openai", "two", {"api_key": "sk-x", "base_url": "http://h"})],
    )
    listed = await service.order_backup_models(["b"])
    assert [b.id for b in listed] == ["b", "a"]
    assert listed[0].secrets_set == ["api_key"] and listed[0].values == {"base_url": "http://h"}
    assert listed[1].uses_main_values
    assert (await backups.load(store, box))[0].values["api_key"] == "sk-x"
    assert [b.id for b in await service.remove_backup_model("b")] == ["a"]
