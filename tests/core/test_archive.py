"""Starting a new conversation archives the one being left, in the background."""

import asyncio

from tests.conftest import collect


async def _drain(service):
    await asyncio.gather(*service._background)


async def test_new_thread_archives_the_previous_conversation(service, digests):
    session = await service.session("u", "cli")
    for text in ["remember the dentist", "and I use LangGraph"]:
        await collect(service.send(session, text))
    await service.new_thread("u")
    await _drain(service)
    assert len(digests.inputs) == 1 and "LangGraph" in digests.inputs[0].transcript
    assert (await service.memory_snapshot("u")).episodes == ["episode 1"]


async def test_short_conversation_is_not_archived(service, digests):
    await collect(service.send(await service.session("u", "cli"), "just one"))
    await service.new_thread("u")
    await _drain(service)
    assert digests.inputs == []
