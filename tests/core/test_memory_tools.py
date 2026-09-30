"""The agent's memory tools and the read-only memory snapshot."""

from tests.conftest import collect


async def test_remember_update_profile_and_forget(service, script):
    script.call("remember", fact="dentist on Friday").call(
        "update_profile", section="interests", items=["LangGraph"]
    ).reply("noted")
    session = await service.session("u", "cli")
    await collect(service.send(session, "remember things"))
    snapshot = await service.memory_snapshot("u")
    assert snapshot.facts == ["dentist on Friday"]
    assert snapshot.profile == {"interests": ["LangGraph"]}
