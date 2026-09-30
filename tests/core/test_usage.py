"""Every tool call is recorded: status, skill name for use_skill, and approvals counted once."""

from assistant.core.config import settings
from assistant.core.events import ApprovalRequired
from assistant.core.skills import store as skills
from tests.conftest import collect


def _by_name(items):
    return {u.name: u for u in items}


async def test_tool_and_skill_usage_is_recorded(service, script, isolated_settings, monkeypatch):
    monkeypatch.setattr(settings, "skills_dir", str(isolated_settings / "skills"))
    skills.save("news-digest", "Daily news", "1. Search")
    script.call("bash", command="echo hi").call("use_skill", name="news-digest").call("use_skill", name="nope").reply(
        "done"
    )
    await collect(service.send(await service.session("u", "cli"), "go"))
    await service.new_thread("u")
    script.call("bash", command="rm -rf build").reply("could not")
    await collect(service.send(await service.session("u", "worker"), "clean up"))

    report = await service.usage_report(days=7)
    tools = _by_name(report.tools)
    assert tools["bash"].calls == 2 and tools["bash"].denied == 1
    assert tools["use_skill"].calls == 2
    assert _by_name(report.skills)["news-digest"].calls == 1


async def test_a_call_paused_for_approval_is_counted_once(service, script):
    script.call("bash", command="rm -rf build").reply("done")
    session = await service.session("u", "cli")
    events = await collect(service.send(session, "clean up"))
    approval = next(e for e in events if isinstance(e, ApprovalRequired))
    await collect(service.resume(session, {approval.interrupt_id: {"approved": True}}))
    bash = _by_name((await service.usage_report()).tools)["bash"]
    assert bash.calls == 1 and bash.denied == 0 and bash.errors == 0
