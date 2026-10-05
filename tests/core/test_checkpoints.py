"""Old checkpoints are pruned when a run ends: the latest of each namespace stays, with every message
and what an interrupted run resumes from."""

import pytest
from langgraph.channels import DeltaChannel

from assistant.core import checkpoints
from assistant.core.events import ApprovalRequired, ToolFinished
from tests.conftest import collect


@pytest.fixture
def skills_dir(isolated_settings, monkeypatch):
    monkeypatch.setattr("assistant.core.config.settings.skills_dir", str(isolated_settings / "skills"))


async def _counts(service, thread_id):
    saver = service._storage.checkpointer
    async with saver.conn.execute(
        "SELECT checkpoint_ns, COUNT(*) FROM checkpoints WHERE thread_id = ? GROUP BY checkpoint_ns", (thread_id,)
    ) as cursor:
        return dict(await cursor.fetchall())


async def test_a_run_leaves_one_checkpoint_with_every_message(service, script):
    script.call("bash", command="echo one").call("bash", command="echo two").reply("done").reply("again")
    session = await service.session("owner", "cli")
    await collect(service.send(session, "run two commands"))
    await collect(service.send(session, "and reply"))
    assert await _counts(service, session.thread_id) == {"": 1}
    shown = await service.conversation_messages(session.thread_id)
    assert [m.role for m in shown if m.role == "user"] == ["user", "user"]
    assert shown[-1].text == "again"


async def test_a_run_waiting_for_approval_resumes_after_pruning(service, script, skills_dir):
    script.call("save_skill", name="digest", description="Daily digest", instructions="1. Read").reply("saved")
    session = await service.session("owner", "cli")
    events = await collect(service.send(session, "make a skill"))
    approval = next(e for e in events if isinstance(e, ApprovalRequired))
    assert await _counts(service, session.thread_id) == {"": 1}
    resumed = await collect(service.resume(session, {approval.interrupt_id: {"approved": True}}))
    assert any(isinstance(e, ToolFinished) and e.output.startswith("Saved skill digest") for e in resumed)


async def test_conversations_saved_before_pruning_are_pruned_at_start(service, script):
    script.reply("one").reply("two")
    session = await service.session("owner", "cli")
    await collect(service.send(session, "hi"))
    graph_config = {"configurable": {"thread_id": session.thread_id}}
    await service._graph.aupdate_state(graph_config, {"last_activity": "2026-10-05T00:00:00+00:00"})
    assert (await _counts(service, session.thread_id))[""] == 2
    assert await checkpoints.prunable(service._storage.checkpointer) == [session.thread_id]
    assert await service.prune_checkpoints() == 1
    assert await _counts(service, session.thread_id) == {"": 1}


def test_the_graph_keeps_no_channel_rebuilt_from_older_checkpoints(service):
    assert not any(isinstance(channel, DeltaChannel) for channel in service._graph.channels.values())
