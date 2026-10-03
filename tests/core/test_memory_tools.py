"""The agent's memory tools and the read-only memory snapshot."""

from assistant.core.memory import profile
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


async def test_a_full_profile_section_is_not_saved(service, script):
    items = [f"topic {i}" for i in range(profile.MAX_ITEMS + 1)]
    script.call("update_profile", section="interests", items=items).reply("noted")
    session = await service.session("u", "cli")
    await collect(service.send(session, "I like many things"))
    assert (await service.memory_snapshot("u")).profile == {}


async def test_old_profiles_move_into_the_current_sections(service):
    likes = [f"like {i}" for i in range(profile.MAX_ITEMS)]
    old = {"wants": ["ship v1"], "likes": likes, "interests": ["chess", "like 0"], "projects": ["lo9i"]}
    old |= {"technical_level": ["senior Python"], "work": [], "dislikes": ["emoji"]}
    await service.store.aput(profile.namespace("u"), "profile", old)
    await profile.migrate(service.store)
    snapshot = await service.memory_snapshot("u")
    assert snapshot.profile == {
        "goals": ["ship v1"],
        "interests": likes,
        "dislikes": ["emoji"],
        "work": ["lo9i", "senior Python"],
    }
    assert snapshot.facts == ["chess"]  # beyond the section's limit
