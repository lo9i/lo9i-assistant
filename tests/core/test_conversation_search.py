"""Searching past conversations: what gets indexed, when, and the agent's search tool."""

from langchain_core.messages import ToolMessage

from assistant.core.agent import Session
from assistant.core.context import UNATTENDED_CHANNEL
from tests.conftest import collect


async def _say(service, text, session=None):
    await collect(service.send(session or await service.session("owner", "cli"), text))


async def _search(service, query):
    return await service._storage.search.search("owner", query, 10)


async def test_what_the_user_and_assistant_wrote_is_searchable_after_each_run(service, script):
    script.call("remember", fact="dentist on Friday").reply("Booked Dr. Pérez for Friday")
    await _say(service, "my dentist appointment is on Friday")
    [found] = await _search(service, "dentist appointment")
    assert found.role == "user" and found.snippet == "my dentist appointment is on Friday"
    assert len(found.at) == len("2026-09-30 14:05")
    [reply] = await _search(service, "perez")  # accents don't matter
    assert reply.role == "assistant" and reply.at == found.at
    assert await _search(service, "cli") == []  # turn headers aren't indexed
    assert await _search(service, "Saved") == []  # tool outputs aren't either


async def test_each_message_is_indexed_once(service):
    session = await service.session("owner", "cli")
    await _say(service, "pick up the parcel", session)
    await _say(service, "and the parcel for mom", session)
    assert len(await _search(service, "parcel")) == 2


async def test_queries_with_punctuation_or_search_keywords_are_plain_words(service):
    await _say(service, "send the e-mail AND call NEAR noon")
    assert len(await _search(service, 'e-mail AND "(NEAR')) == 1
    assert await _search(service, "?!") == []


async def test_messages_not_yet_indexed_are_caught_up(service):
    session = await service.session("owner", "cli")
    await _say(service, "the wifi password is on the fridge", session)
    await service._storage.search.remove(session.thread_id)  # as saved before search existed
    assert await service.index_messages("owner") == 2
    assert len(await _search(service, "fridge")) == 1
    assert await service.index_messages("owner") == 0


async def test_deleting_a_conversation_removes_it_from_search(service):
    session = await service.session("owner", "cli")
    await _say(service, "my locker code is 4512", session)
    await service.delete_conversation("owner", session.thread_id)
    assert await _search(service, "locker") == []


async def test_the_agent_finds_earlier_conversations_and_job_runs(service, script, titles):
    await collect(service.send(Session("owner", UNATTENDED_CHANNEL, "job:news:1"), "check the weather in Madrid"))
    await _say(service, "I flew to Madrid last spring")
    await service.new_channel_thread("owner", "cli")
    script.call("search_conversations", query="Madrid trip").reply("found it")
    await _say(service, "when was I in Madrid?")
    [result] = [m for m in script.requests[-1] if isinstance(m, ToolMessage)]
    lines = str(result.content).splitlines()
    assert any('in "Trip to Rome", user: I flew to Madrid last spring' in line for line in lines)
    assert any('in "job:news:1", user: check the weather in Madrid' in line for line in lines)
