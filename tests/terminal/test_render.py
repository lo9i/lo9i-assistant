"""The plain REPL's printer: what a run waits on and where home sent its message on."""

from assistant.core.events import ApprovalRequired, Dispatched, Done, UserSaid, UserTaken
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


async def test_a_message_the_agent_gets_to_later_says_its_waiting_and_then_that_it_got_to_it(capsys):
    await render(_events(UserSaid("skip the slow tests\nplease", id="m1", waiting=True), UserTaken("m1"), Done()))
    out = capsys.readouterr().out
    assert "waiting for the agent to get to it" in out and "The agent got to: skip the slow tests" in out
