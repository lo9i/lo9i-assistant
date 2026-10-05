"""Saved facts and past conversations, edited and deleted from the apps."""

import pytest

from assistant.core.agent import MemoryEditError, MemoryNotFoundError
from assistant.core.memory import episodes, facts
from assistant.core.memory.episodes import Episode


async def test_facts_are_listed_newest_first_and_an_edit_keeps_when_it_was_saved(service):
    old = await facts.add(service.store, "u", "drives a red car")
    await facts.add(service.store, "u", "likes jazz")
    assert [f.text for f in await service.saved_facts("u")] == ["likes jazz", "drives a red car"]
    edited = await service.edit_fact("u", old, "  drives a blue car ")
    assert edited.id != old and edited.text == "drives a blue car"
    assert [f.text for f in await service.saved_facts("u")] == ["likes jazz", "drives a blue car"]


async def test_an_edited_fact_is_found_by_its_new_text(service):
    fact_id = await facts.add(service.store, "u", "drives a red car")
    await service.memory_index.sync_all()
    await service.edit_fact("u", fact_id, "plays the violin on Sundays")
    assert await service.memory_index.sync_all() == 1
    found = await service._recall.search("u", "violin Sundays", 1, 0)
    assert [f.text for f in found.facts] == ["plays the violin on Sundays"]
    assert list(await service._storage.vectors.indexed("u")) == [("fact", found.facts[0].id)]


async def test_facts_and_episodes_are_deleted(service):
    fact_id = await facts.add(service.store, "u", "likes jazz")
    await episodes.save(service.store, "u", Episode("2026-10-01T09:00", "2026-10-01T10:00", "Planned a trip"))
    episode_id = (await service.saved_episodes("u"))[0].id
    await service.delete_fact("u", fact_id)
    await service.delete_episode("u", episode_id)
    assert await service.saved_facts("u") == [] and await service.saved_episodes("u") == []
    with pytest.raises(MemoryNotFoundError):
        await service.delete_fact("u", fact_id)
    with pytest.raises(MemoryNotFoundError):
        await service.edit_episode("u", episode_id, "anything")


async def test_an_episode_edit_keeps_its_times_and_empty_text_is_refused(service):
    await episodes.save(service.store, "u", Episode("2026-10-01T09:00", "2026-10-01T10:00", "Planned a trip"))
    await episodes.save(service.store, "u", Episode("2026-10-02T09:00", "2026-10-02T10:00", "Fixed the bike"))
    newest, older = await service.saved_episodes("u")
    assert newest.summary == "Fixed the bike"
    edited = await service.edit_episode("u", older.id, "Planned a trip to Rome")
    assert (edited.started_at, edited.ended_at) == (older.started_at, older.ended_at)
    assert [e.summary for e in await service.saved_episodes("u")] == ["Fixed the bike", "Planned a trip to Rome"]
    with pytest.raises(MemoryEditError, match="Write something"):
        await service.edit_episode("u", edited.id, "   ")
