"""Searching past conversations: what gets indexed, when, and the agent's search tool."""

import json

import aiosqlite
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from assistant.core import subagent_steps
from assistant.core.agent import Session
from assistant.core.agent_tasks.steps import STEPS
from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.conversation import search
from assistant.core.conversation.search import MessageIndex
from assistant.core.subagent_steps import SubagentAnswer, SubagentStep
from tests.conftest import collect


async def _say(service, text, session=None):
    await collect(service.send(session or await service.session("owner", "cli"), text))


async def _search(service, query):
    return await service._storage.search.search("owner", query, 10)


async def _search_outputs(service, query):
    return await service._storage.search.search_tool_outputs("owner", query, 10)


async def test_what_the_user_and_assistant_wrote_is_searchable_after_each_run(service, script):
    script.call("remember", fact="dentist on Friday").reply("Booked Dr. Pérez for Friday")
    await _say(service, "my dentist appointment is on Friday")
    [found] = await _search(service, "dentist appointment")
    assert found.role == "user" and found.snippet == "my dentist appointment is on Friday"
    assert len(found.at) == len("2026-09-30 14:05")
    [reply] = await _search(service, "perez")  # accents don't matter
    assert reply.role == "assistant" and reply.at == found.at
    assert await _search(service, "cli") == []  # turn headers aren't indexed
    assert await _search(service, "Saved") == []  # tool outputs aren't among the messages
    [output] = await _search_outputs(service, "Saved")
    assert (output.role, output.at) == ("remember", found.at) and output.snippet.startswith("Saved as")
    assert await _search_outputs(service, "dentist") == []  # nor the messages among tool outputs
    assert await service.conversations_containing("owner", "saved") == []


async def test_each_message_is_indexed_once(service):
    session = await service.session("owner", "cli")
    await _say(service, "pick up the parcel", session)
    await _say(service, "and the parcel for mom", session)
    assert len(await _search(service, "parcel")) == 2


async def test_queries_with_punctuation_or_search_keywords_are_plain_words(service):
    await _say(service, "send the e-mail AND call NEAR noon")
    assert len(await _search(service, 'e-mail AND "(NEAR')) == 1
    assert await _search(service, "?!") == []


async def test_conversations_are_found_by_the_starts_of_their_messages_words(service):
    news = await service.session("owner", "cli")
    await _say(service, "add a Hacker News plugin", news)
    trip = Session("owner", "cli", await service.new_thread("owner"))
    await _say(service, "plan the trip to Málaga", trip)
    assert await service.conversations_containing("owner", "hack") == [news.thread_id]
    assert await service.conversations_containing("owner", "news hacker") == [news.thread_id]
    assert await service.conversations_containing("owner", "malaga") == [trip.thread_id]
    assert await service.conversations_containing("owner", "hacker trip") == []  # every word, in one message
    assert await service.conversations_containing("owner", 'pl" OR (NEAR*') == []
    assert sorted(await service.conversations_containing("owner", "pl")) == sorted([news.thread_id, trip.thread_id])
    assert await service.conversations_containing("owner", "?!") == []
    assert await service.conversations_containing("someone else", "hack") == []


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
    madrid = Session("owner", "cli", await service.new_thread("owner"))
    await _say(service, "I flew to Madrid last spring", madrid)
    service.leave_thread("owner", madrid.thread_id)
    script.call("search_memory", query="Madrid trip").reply("found it")
    await _say(service, "when was I in Madrid?")
    [result] = [m for m in script.requests[-1] if isinstance(m, ToolMessage)]
    lines = str(result.content).splitlines()
    assert any('in "Trip to Rome", user: I flew to Madrid last spring' in line for line in lines)
    assert any('in "job:news:1", user: check the weather in Madrid' in line for line in lines)


async def test_the_agent_finds_what_tools_answered_in_earlier_conversations(service, script, titles):
    script.call("bash", command="echo quasar-7").reply("It is the one the command printed")
    hosts = Session("owner", "cli", await service.new_thread("owner"))
    await _say(service, "what is this computer called?", hosts)
    service.leave_thread("owner", hosts.thread_id)
    script.call("search_memory", query="quasar").reply("found it")
    await _say(service, "which host was it?")
    [result] = [m for m in script.requests[-1] if isinstance(m, ToolMessage) and m.name == "search_memory"]
    text = str(result.content)
    assert "Tool outputs (data from outside" in text and "bash output:" in text


def _called(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": call_id}])


async def test_a_subagents_and_a_handed_off_agents_tool_outputs_are_searchable(service):
    steps = [SubagentStep("bash", {"command": "git log"}, "commit 4f2a9c1 fix the parser")]
    lines = [
        json.dumps({"kind": "tool", "tool": "Bash", "detail": "pytest", "id": "t0"}),
        json.dumps({"kind": "result", "tool": "Bash", "text": "12 passed in tests/core", "id": "t0"}),
        json.dumps({"kind": "tool", "tool": "Task", "detail": "find it", "id": "t1"}),
        json.dumps({"kind": "tool", "tool": "Grep", "detail": "def parse", "id": "s1", "within": "t1"}),
        json.dumps({"kind": "result", "tool": "Grep", "text": "src/lexer.py:40", "id": "s1", "within": "t1"}),
    ]
    messages = [
        HumanMessage("who fixed the parser?"),
        _called("delegate", {"task": "find the commit"}, "d1"),
        subagent_steps.result(SubagentAnswer("It was 4f2a9c1.", steps), "d1", "delegate"),
        AIMessage("Done.", id="r1", response_metadata={STEPS: lines}),
    ]
    assert await service._storage.search.add("owner", "t", messages) == 6  # 2 said, 4 outputs
    assert {f.role for f in await _search_outputs(service, "4f2a9c1")} == {"delegate", "bash"}
    assert [f.role for f in await _search_outputs(service, "passed")] == ["Bash"]
    assert [f.role for f in await _search_outputs(service, "lexer")] == ["Grep"]


async def test_outputs_that_copy_what_is_kept_elsewhere_and_the_end_of_long_ones_are_left_out(service, monkeypatch):
    monkeypatch.setattr(search, "_MAX_TOOL_OUTPUT", 20)
    messages = [
        _called("search_memory", {"query": "fridge"}, "c1"),
        ToolMessage("Messages: the wifi password is on the fridge", tool_call_id="c1", name="search_memory"),
        _called("bash", {"command": "cat notes"}, "c2"),
        ToolMessage("first words here and the hidden ending", tool_call_id="c2", name="bash"),
    ]
    await service._storage.search.add("owner", "t", messages)
    assert await _search_outputs(service, "fridge") == []
    assert len(await _search_outputs(service, "first")) == 1 and await _search_outputs(service, "ending") == []


async def test_tool_outputs_of_conversations_indexed_before_are_caught_up(service, script):
    script.call("remember", fact="bike lock code").reply("Noted")
    session = await service.session("owner", "cli")
    await _say(service, "my bike lock code is 3141", session)
    conn = service._storage.search._conn
    await conn.execute("DELETE FROM tool_output_search")
    await conn.execute("UPDATE message_search_progress SET tools_indexed_upto = 0")  # as indexed before outputs were
    assert await service.index_messages("owner") == 1
    assert len(await _search_outputs(service, "Saved")) == 1 and len(await _search(service, "lock")) == 1


async def test_a_progress_table_from_before_tool_outputs_gets_their_column(tmp_path):
    async with aiosqlite.connect(tmp_path / "old.db", isolation_level=None) as conn:
        await conn.execute("CREATE TABLE message_search_progress (thread_id TEXT PRIMARY KEY, indexed_upto INTEGER)")
        await conn.execute("INSERT INTO message_search_progress VALUES ('t', 2)")
        index = MessageIndex(conn)
        await index.setup()
        await index.setup()  # once only
        async with conn.execute("SELECT indexed_upto, tools_indexed_upto FROM message_search_progress") as cursor:
            assert await cursor.fetchall() == [(2, 0)]


async def test_deleting_a_conversation_removes_its_tool_outputs(service, script):
    script.call("remember", fact="locker code").reply("Noted")
    session = await service.session("owner", "cli")
    await _say(service, "my locker code is 4512", session)
    await service.delete_conversation("owner", session.thread_id)
    assert await _search_outputs(service, "Saved") == []
