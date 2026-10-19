"""Searching saved facts and episodes by meaning: the index, its sync, and search_memory."""

import asyncio

from langchain_core.messages import ToolMessage

from assistant.core.config import settings
from assistant.core.memory import episodes, facts
from assistant.core.memory.episodes import Episode
from tests.conftest import collect


async def _fact(service, text, user="owner"):
    return await facts.add(service.store, user, text)


async def _episode(service, summary, ended_at="2026-09-01T10:00:00"):
    await episodes.save(service.store, "owner", Episode("2026-09-01T09:00:00", ended_at, summary))


async def _recall(service, query):
    return await service._recall.search("owner", query, 5, 3)


async def _indexed(service, user="owner"):
    return await service._storage.vectors.indexed(user)


async def test_facts_and_episodes_are_found_by_meaning_after_a_sync(service):
    await _fact(service, "the car goes to the garage on Tuesday")
    await _fact(service, "prefers window seats")
    await _episode(service, "Planned the garage visit for the car")
    assert await service.memory_index.sync_all() == 3
    found = await _recall(service, "car garage")
    assert found.facts[0].text == "the car goes to the garage on Tuesday"
    assert [e.summary for e in found.episodes] == ["Planned the garage visit for the car"]
    assert await service.memory_index.sync_all() == 0


async def test_a_sync_drops_deleted_memories_and_search_skips_them_before_it(service):
    kept = await _fact(service, "likes green tea")
    gone = await _fact(service, "likes black tea")
    await service.memory_index.sync_all()
    await facts.remove(service.store, "owner", gone)
    assert [f.id for f in (await _recall(service, "tea")).facts] == [kept]
    await service.memory_index.sync_all()
    assert set(await _indexed(service)) == {("fact", kept)}


async def test_vectors_from_another_model_are_made_again(service, embedder):
    await _fact(service, "allergic to peanuts")
    await service.memory_index.sync_all()
    embedder.model = "fake-embedder-v2"
    assert (await _recall(service, "peanuts")).facts == []  # old vectors aren't compared
    assert await service.memory_index.sync_all() == 1
    assert set((await _indexed(service)).values()) == {"fake-embedder-v2"}


async def test_every_user_is_synced_and_searched_apart(service):
    await _fact(service, "owner's locker is 12")
    await _fact(service, "guest's locker is 40", user="guest")
    assert await service.memory_index.sync_all() == 2
    assert [f.text for f in (await _recall(service, "locker")).facts] == ["owner's locker is 12"]


async def test_the_running_index_follows_memory_changes(service):
    stop = asyncio.Event()
    running = asyncio.create_task(service.memory_index.run(stop))
    fact_id = await _fact(service, "the gate code is 1990")
    try:
        await _until(lambda: _has(service, fact_id))
    finally:
        stop.set()
        await running


async def test_a_failed_sync_is_logged_and_retried_on_the_next_change(service, embedder, caplog):
    embedder.failing = True
    stop = asyncio.Event()
    running = asyncio.create_task(service.memory_index.run(stop))
    await _fact(service, "first")
    try:
        await _until(lambda: _logged(caplog, "Couldn't make memories searchable"))
        embedder.failing = False
        second = await _fact(service, "second")
        await _until(lambda: _has(service, second))
    finally:
        stop.set()
        await running
    assert len(await _indexed(service)) == 2


async def test_the_prompt_keeps_the_most_recent_facts_and_episodes(service, monkeypatch):
    for text in ["oldest", "middle", "newest"]:
        await _fact(service, text)
        await _episode(service, text, ended_at=f"2026-09-0{['oldest', 'middle', 'newest'].index(text) + 1}")
    monkeypatch.setattr(settings, "memory_max_facts", 2)
    monkeypatch.setattr(settings, "memory_max_episodes", 2)
    snapshot = await service.memory_snapshot("owner")
    assert sorted(snapshot.facts) == ["middle", "newest"]
    assert snapshot.episodes == ["middle", "newest"]


async def test_search_memory_returns_facts_summaries_and_messages(service, script):
    await _fact(service, "passport renewal is due in March")
    await _episode(service, "Talked about renewing the passport")
    await service.memory_index.sync_all()
    script.call("search_memory", query="passport renewal").reply("found it")
    await collect(service.send(await service.session("owner", "cli"), "when is my passport renewal?"))
    result = _tool_result(script)
    assert "Saved facts:\n- [" in result and "] passport renewal is due in March" in result
    assert "Past conversation summaries:\n- 2026-09-01T09:00 to 2026-09-01T10:00: Talked about renewing" in result
    assert "Messages: none with these words." in result


async def test_search_memory_still_searches_messages_when_the_model_fails(service, script, embedder):
    await collect(service.send(await service.session("owner", "cli"), "my bike lock code is 7781"))
    embedder.failing = True
    script.call("search_memory", query="bike lock").reply("found it")
    await collect(service.send(await service.session("owner", "cli"), "what's my bike lock code?"))
    result = _tool_result(script)
    assert "couldn't be searched: the model couldn't be downloaded" in result
    assert "user: my bike lock code is 7781" in result


def _tool_result(script) -> str:
    [result] = [m for m in script.requests[-1] if isinstance(m, ToolMessage)]
    return str(result.content)


async def _has(service, fact_id) -> bool:
    return ("fact", fact_id) in await _indexed(service)


def _logged(caplog, text) -> bool:
    return any(text in record.getMessage() for record in caplog.records)


async def _until(condition) -> None:
    """Waits for the background index to catch up."""
    for _ in range(200):
        result = condition()
        if await result if asyncio.iscoroutine(result) else result:
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("the index never caught up")


async def _archive_saying(service, texts):
    session = await service.session("owner", "telegram")
    for text in texts:
        await collect(service.send(session, text))
    service.leave_thread("owner", session.thread_id)
    await asyncio.gather(*service._background)
    await service.memory_writer.write_all()


async def test_the_digest_also_gets_older_facts_close_to_what_the_user_said(service, digests, monkeypatch):
    monkeypatch.setattr(settings, "memory_max_facts", 1)
    monkeypatch.setattr("assistant.core.conversation.memory_writer._RELATED_PER_MESSAGE", 1)
    await _fact(service, "the car goes to the garage on Tuesday")
    await _fact(service, "likes jazz records")
    await _fact(service, "prefers window seats")  # the most recent, the one the digest always gets
    await service.memory_index.sync_all()
    await _archive_saying(service, ["the car needs the garage again", "the garage for the car, Tuesday?"])
    given = [f.text for f in digests.inputs[0].facts]
    assert given == ["prefers window seats", "the car goes to the garage on Tuesday"]


async def test_without_the_embedding_model_the_digest_gets_the_recent_facts(service, digests, monkeypatch):
    from assistant.core.memory.embedder import EmbeddingError

    async def unavailable(user_id, texts, limit_each):
        raise EmbeddingError("the model is still downloading")

    monkeypatch.setattr(service._recall, "facts_near", unavailable)
    await _fact(service, "prefers window seats")
    await _archive_saying(service, ["book a flight", "a window seat please"])
    assert [f.text for f in digests.inputs[0].facts] == ["prefers window seats"]
