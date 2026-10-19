"""Leaving a conversation archives it, in the background."""

import asyncio

from assistant.core.agent import Session
from tests.conftest import collect


async def _drain(service):
    await asyncio.gather(*service._background)
    await service.memory_writer.write_all()


async def test_a_channel_writing_in_another_conversation_archives_the_previous_one(service, digests):
    session = Session("u", "telegram", await service.new_thread("u"))
    for text in ["remember the dentist", "and I use LangGraph"]:
        await collect(service.send(session, text))
    await service.channel_wrote("u", "telegram", session.thread_id)
    await service.channel_wrote("u", "telegram", await service.new_thread("u"))
    await _drain(service)
    assert len(digests.inputs) == 1 and "LangGraph" in digests.inputs[0].transcript
    assert (await service.memory_snapshot("u")).episodes == ["episode 1"]


async def test_short_conversation_is_not_archived(service, digests):
    session = await service.session("u", "cli")
    await collect(service.send(session, "just one"))
    service.leave_thread("u", session.thread_id)
    await _drain(service)
    assert digests.inputs == []
