"""A run that fails is marked in its conversation: history shows the error it ended with, a stopped run doesn't
look like it, and no model call sends the mark."""

import sqlite3
from typing import Any

from langchain_core.messages import AIMessage

from assistant.core.conversation import failed
from assistant.core.events import Error
from assistant.core.memory import profile
from tests.conftest import collect


async def _locked(*args: Any, **kwargs: Any) -> None:
    raise sqlite3.OperationalError("database is locked")


async def test_a_failed_run_shows_its_error_in_history_and_the_next_run_goes_on(service, script, monkeypatch):
    monkeypatch.setattr(profile, "save", _locked)
    script.call("update_profile", section="goals", items=["run a marathon"]).reply("It didn't save.")
    session = await service.session("owner", "cli")
    events = await collect(service.send(session, "remember my goal"))
    assert any(isinstance(e, Error) for e in events)
    shown = [(m.role, m.text) for m in await service.conversation_messages(session.thread_id)]
    assert shown[-1] == ("error", "OperationalError: database is locked")
    await collect(service.send(session, "did it save?"))
    sent = script.requests[-1]
    assert not any(isinstance(m, AIMessage) and failed.of(m) for m in sent)
    assert "update_profile didn't finish" in sent[-2].text  # the call it left, answered with a stub
