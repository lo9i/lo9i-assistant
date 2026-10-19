"""The plain REPL's printer: what a run waits on and where home sent its message on."""

from assistant.core.events import ApprovalRequired, Dispatched, Done
from assistant_terminal.render import render


async def _events(*events):
    for event in events:
        yield event


async def test_a_run_returns_what_it_waits_on_and_where_home_sent_its_message(capsys):
    dispatched = Dispatched("d1", "t1", "Taxes", "what about my taxes?", "→ Continued in “Taxes”.")
    shown = await render(_events(dispatched, ApprovalRequired("i1", {"tool": "bash"}), Done()))
    assert shown.dispatched == dispatched and [a.interrupt_id for a in shown.approvals] == ["i1"]
    assert "→ Continued in “Taxes”." in capsys.readouterr().out
