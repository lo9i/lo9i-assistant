"""The plain REPL's printer: what a run waits on and where home sent its message on."""

from assistant.core.events import ApprovalRequired, Dispatched, Done, UserSaid
from assistant_terminal.render import render


async def _events(*events):
    for event in events:
        yield event


async def test_a_run_returns_what_it_waits_on_and_where_home_sent_its_message(capsys):
    dispatched = Dispatched("d1", "t1", "Taxes", "what about my taxes?", "→ Continued in “Taxes”.")
    shown = await render(_events(dispatched, ApprovalRequired("i1", {"tool": "bash"}), Done()))
    assert shown.dispatched == dispatched and [a.interrupt_id for a in shown.approvals] == ["i1"]
    assert "→ Continued in “Taxes”." in capsys.readouterr().out


async def test_a_message_sent_to_an_agent_at_work_shows_with_its_files(capsys):
    await render(_events(UserSaid("see this", ["shot.png"]), Done()))
    out = capsys.readouterr().out
    assert "> see this" in out and "📎 shot.png" in out
