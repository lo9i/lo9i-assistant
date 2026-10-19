"""The inbox routes each message without asking: the worker model picks where (a fake classifier here), a
quick question is answered in the inbox, anything else goes on in the conversation it continues or a new
one when the model isn't sure enough, and the client that sent it sends it there by its id, files
included. A quick exchange that goes on is carried to a new conversation."""

from langchain_openai.chat_models.base import _convert_message_to_dict

from assistant.core import conversations
from assistant.core.agent import AssistantService, Session
from assistant.core.attachments import Attachment, is_reference
from assistant.core.conversation import dispatch_setting, ended
from assistant.core.conversation.dispatch import FOLLOW_UP, QUICK, Candidate, Pick, candidates, parse
from assistant.core.conversation.dispatch_nodes import INBOX_TURNS
from assistant.core.conversation.dispatch_setting import DispatchSetting
from assistant.core.conversations import Conversation
from assistant.core.events import ApprovalRequired, Dispatched, Error
from tests.conftest import collect

_CANDIDATES = [Candidate("t1", "Trip to Rome", ["rome"], ""), Candidate("t2", "Taxes", ["taxes"], "")]


async def _side(service: AssistantService, thread_id: str, title: str, tags: list[str], updated_at: str) -> None:
    record = Conversation(thread_id, title, updated_at, updated_at, tags=tags)
    await conversations.save(service.store, "owner", record)


async def _inbox(service: AssistantService) -> Session:
    return await service.session("owner", "web")


def test_the_reply_names_the_pick_how_sure_and_what_else():
    assert parse("Pick: 2\nConfidence: 0.9\nElse: 0", _CANDIDATES) == Pick("t2", 0.9, "")
    assert parse("**Pick:** 1\nConfidence: 1.4\nElse: 2", _CANDIDATES) == Pick("t1", 1.0, "t2")
    assert parse("Pick: 7\nConfidence: 0.95\nElse: 1", _CANDIDATES) == Pick("", 0.95, "t1")
    assert parse("Pick: Q\nConfidence: 0.9\nElse: 0", _CANDIDATES) == Pick(QUICK, 0.9, "")


def test_a_follow_up_is_one_only_while_the_inbox_has_an_exchange_going_on():
    assert parse("Pick: F\nConfidence: 0.9\nElse: 1", _CANDIDATES, exchange=True) == Pick(FOLLOW_UP, 0.9, "t1")
    assert parse("Pick: f\nConfidence: 0.9\nElse: 1", _CANDIDATES) == Pick(QUICK, 0.9, "t1")


def test_a_reply_that_cant_be_read_is_a_new_conversation_nobody_is_sure_of():
    assert parse("I think it's about Rome.", _CANDIDATES) == Pick("", 0.0, "")


async def test_the_candidates_are_those_the_words_match_then_the_most_recent(service):
    inbox = await _inbox(service)
    await _side(service, "t1", "Trip to Rome", ["rome"], "2026-10-01T10:00:00+00:00")
    await _side(service, "t2", "Taxes", ["taxes"], "2026-10-03T10:00:00+00:00")
    await _side(service, "t3", "Garden", ["garden"], "2026-10-02T10:00:00+00:00")
    found = await candidates(service.store, service._storage.search, "owner", inbox.thread_id, "flights to Rome?")
    assert [c.thread_id for c in found] == ["t1", "t2", "t3"]
    assert found[0].active.endswith("days ago")


async def test_an_archived_conversation_is_never_a_candidate(service):
    inbox = await _inbox(service)
    await _side(service, "t1", "Trip to Rome", ["rome"], "2026-10-01T10:00:00+00:00")
    await conversations.archive(service.store, "owner", "t1", "Home (before the inbox)")
    assert await candidates(service.store, service._storage.search, "owner", inbox.thread_id, "Rome") == []


async def test_a_sure_pick_sends_the_message_on_without_a_model_call(dispatch, service, script):
    inbox = await _inbox(service)
    await _side(service, "t1", "Trip to Rome", ["rome"], "2026-10-01")
    dispatch.picks.append(Pick("t1", 0.95, ""))
    events = await collect(service.send(inbox, "book the flights to Rome"))
    [sent] = [e for e in events if isinstance(e, Dispatched)]
    assert (sent.thread_id, sent.title, sent.text) == ("t1", "Trip to Rome", "book the flights to Rome")
    assert dispatch.inputs[0][0] == "book the flights to Rome" and script.requests == []
    shown = [(m.role, m.text) for m in await service.conversation_messages(inbox.thread_id)]
    assert shown == [("user", "book the flights to Rome"), ("assistant", "→ Continued in “Trip to Rome”.")]


async def test_the_message_sent_on_runs_where_it_went_once(dispatch, service, script):
    inbox = await _inbox(service)
    events = await collect(service.send(inbox, "plan my week"))
    [sent] = [e for e in events if isinstance(e, Dispatched)]
    assert sent.thread_id == "" and sent.title == "New conversation"
    side = Session("owner", "web", await service.new_thread("owner"))
    script.reply("Here's a plan.")
    await collect(service.send_dispatched(side, sent.id))
    [request] = script.requests
    assert "plan my week" in str(request[-1].content)
    assert [m.text for m in await service.conversation_messages(side.thread_id)] == ["plan my week", "Here's a plan."]
    again = await collect(service.send_dispatched(side, sent.id))
    assert isinstance(again[0], Error)


async def test_files_go_on_with_the_message(dispatch, service, script):
    inbox = await _inbox(service)
    note = Attachment("notes.txt", "text/plain", b"buy milk")
    [sent] = [e for e in await collect(service.send(inbox, "", [note])) if isinstance(e, Dispatched)]
    side = Session("owner", "web", await service.new_thread("owner"))
    script.reply("Noted.")
    await collect(service.send_dispatched(side, sent.id))
    assert "buy milk" in str(script.requests[0][-1].content)  # the file, read for the model
    state = await service._graph.aget_state({"configurable": {"thread_id": side.thread_id}})
    assert any(is_reference(b) for b in state.values["messages"][0].content)  # kept as the same upload


async def test_an_unsure_pick_starts_a_new_conversation_without_asking(dispatch, service):
    inbox = await _inbox(service)
    await _side(service, "t1", "Trip to Rome", ["rome"], "2026-10-01")
    dispatch.picks.append(Pick("t1", 0.5, ""))
    events = await collect(service.send(inbox, "what about Rome?"))
    assert not [e for e in events if isinstance(e, ApprovalRequired)]
    assert [e.thread_id for e in events if isinstance(e, Dispatched)] == [""]


async def test_a_quick_question_is_answered_in_the_inbox(dispatch, service, script):
    inbox = await _inbox(service)
    dispatch.picks.append(Pick(QUICK, 0.9, ""))
    script.reply("It's 3 pm in Tokyo.")
    events = await collect(service.send(inbox, "what time is it in Tokyo?"))
    assert not [e for e in events if isinstance(e, Dispatched)]
    shown = [m.text for m in await service.conversation_messages(inbox.thread_id)]
    assert shown == ["what time is it in Tokyo?", "It's 3 pm in Tokyo."]


async def test_a_quick_exchange_that_goes_on_moves_to_a_new_conversation_with_it(dispatch, service, script):
    inbox = await _inbox(service)
    dispatch.picks.extend([Pick(QUICK, 0.9, ""), *[Pick(FOLLOW_UP, 0.9, "")] * INBOX_TURNS])
    script.reply("150 km.").reply("About 2 hours by car.")
    await collect(service.send(inbox, "how far is Rome from Florence?"))
    await collect(service.send(inbox, "and by car?"))
    assert dispatch.exchanges[1] == "User: how far is Rome from Florence?\nAssistant: 150 km."
    events = await collect(service.send(inbox, "ok, plan the drive for saturday"))
    [sent] = [e for e in events if isinstance(e, Dispatched)]
    assert sent.thread_id == "" and "with the quick exchange" in sent.line
    assert sent.carried.startswith("**You:** how far is Rome from Florence?")
    side = Session("owner", "web", await service.new_thread("owner"))
    script.reply("Here's the plan.")
    await collect(service.send_dispatched(side, sent.id))
    told = str(script.requests[-1][-1].content)
    assert "User: and by car?" in told and "Assistant: About 2 hours by car." in told
    carried, first = (await service.conversation_messages(side.thread_id))[:2]
    assert (carried.role, carried.text) == ("carried", sent.carried)  # shown again after a reload
    assert "**Assistant:** About 2 hours by car." in carried.text
    assert (first.role, first.text) == ("user", "ok, plan the drive for saturday")
    sent_to_model = _convert_message_to_dict(script.requests[-1][-1])  # as OpenAI-compatible models get it
    assert "lo9i_carried" not in str(sent_to_model)  # the model reads the note, not the lines kept to show
    asked = len(dispatch.inputs)
    events = await collect(service.send(inbox, "thanks"))  # the exchange went with it: this follows it up there
    assert [e.thread_id for e in events if isinstance(e, Dispatched)] == [side.thread_id]
    assert len(dispatch.inputs) == asked


async def test_a_short_follow_up_goes_where_the_last_message_went_without_the_model(dispatch, service, script):
    inbox = await _inbox(service)
    await _side(service, "t1", "Trip to Rome", ["rome"], "2026-10-01")
    await _side(service, "t2", "Taxes", ["taxes"], "2026-10-01")
    dispatch.picks.append(Pick("t1", 0.95, ""))
    [sent] = [e for e in await collect(service.send(inbox, "book the flights to Rome")) if isinstance(e, Dispatched)]
    script.reply("Booked.")
    await collect(service.send_dispatched(Session("owner", "web", "t1"), sent.id))
    events = await collect(service.send(inbox, "and a hotel near the station?"))
    assert [e.thread_id for e in events if isinstance(e, Dispatched)] == ["t1"]
    assert len(dispatch.inputs) == 1  # no model call for it
    await collect(service.send(inbox, "what about my taxes?"))  # another conversation's tag: the model picks
    assert len(dispatch.inputs) == 2


async def test_a_follow_up_from_another_channel_or_much_later_goes_to_the_model(dispatch, service, script):
    inbox = await _inbox(service)
    await _side(service, "t1", "Trip to Rome", ["rome"], "2026-10-01")
    dispatch.picks.extend([Pick("t1", 0.95, ""), Pick("t1", 0.95, "")])
    [sent] = [e for e in await collect(service.send(inbox, "book the flights to Rome")) if isinstance(e, Dispatched)]
    script.reply("Booked.")
    await collect(service.send_dispatched(Session("owner", "web", "t1"), sent.id))
    await collect(service.send(Session("owner", "telegram", inbox.thread_id), "and a hotel?"))
    assert len(dispatch.inputs) == 2  # another channel
    await _side(service, "t1", "Trip to Rome", ["rome"], "2026-10-01")  # last written in long ago
    await collect(service.send(Session("owner", "telegram", inbox.thread_id), "and a car?"))
    assert len(dispatch.inputs) == 3


async def test_a_follow_up_on_work_started_in_the_inbox_is_answered_there_not_routed(dispatch, service, script):
    inbox = await _inbox(service)
    await ended.record(service.store, "owner", inbox.thread_id, "mcp:p:b", "The MCP server photos failed")
    script.reply("The conversion failed.")
    events = await collect(service.follow_up(inbox, "⚠️ photos: failed"))
    assert dispatch.inputs == [] and not [e for e in events if isinstance(e, Dispatched)]
    assert [m.role for m in await service.conversation_messages(inbox.thread_id)] == ["notice", "assistant"]


async def test_a_conversation_of_its_own_answers_without_routing(dispatch, service, script):
    side = Session("owner", "web", await service.new_thread("owner"))
    script.reply("Sure.")
    assert not [e for e in await collect(service.send(side, "hi")) if isinstance(e, Dispatched)]
    assert dispatch.inputs == []


async def test_the_setting_keeps_the_confidence_between_0_and_1(service):
    assert await dispatch_setting.load(service.store) == DispatchSetting(0.7)
    saved = await dispatch_setting.save(service.store, DispatchSetting(0.6))
    assert await dispatch_setting.load(service.store) == saved
    try:
        await dispatch_setting.save(service.store, DispatchSetting(1.5))
    except dispatch_setting.DispatchSettingError:
        return
    raise AssertionError("a confidence above 1 was saved")


async def _sent_to_rome(dispatch, service, script) -> tuple[Session, Dispatched]:
    """The inbox sent "book the hotel in Rome" on to the trip, which answered."""
    inbox = await _inbox(service)
    await _side(service, "t1", "Trip to Rome", ["rome"], "2026-10-01")
    await _side(service, "t2", "Hotels", ["rome", "hotel"], "2026-10-02")
    dispatch.picks.append(Pick("t1", 0.95, ""))
    [sent] = [e for e in await collect(service.send(inbox, "book the hotel in Rome")) if isinstance(e, Dispatched)]
    script.reply("Booked.")
    await collect(service.send_dispatched(Session("owner", "web", "t1"), sent.id))
    return inbox, sent


async def test_a_moved_message_goes_on_by_its_id_and_the_conversation_it_left_leaves_it_out(dispatch, service, script):
    inbox, sent = await _sent_to_rome(dispatch, service, script)
    dispatch.picks.append(Pick("t2", 0.99, ""))
    [asked] = [e for e in await collect(service.move_dispatched(inbox)) if isinstance(e, ApprovalRequired)]
    assert [c.thread_id for c in dispatch.inputs[1][1]] == ["t2"]  # not where it is
    assert asked.request["options"] == ["Continue in Hotels", "A new conversation"]
    events = await collect(service.resume(inbox, {asked.interrupt_id: {"choices": ["Continue in Hotels"]}}))
    [moved] = [e for e in events if isinstance(e, Dispatched)]
    assert (moved.id, moved.thread_id, moved.line) == (sent.id, "t2", "→ Moved “book the hotel in Rome” to “Hotels”.")
    script.reply("Booked here.")
    await collect(service.send_dispatched(Session("owner", "web", "t2"), sent.id))
    assert "book the hotel in Rome" in str(script.requests[-1][-1].content)
    script.reply("Sure.")
    await collect(service.send(Session("owner", "web", "t1"), "and the train?"))
    assert "moved these messages" in str(script.requests[-1][-1].content)
    shown = await service.conversation_messages(inbox.thread_id)
    assert [m.dispatch_id for m in shown if m.role == "assistant"] == [sent.id, sent.id]


async def test_a_move_left_unanswered_leaves_the_message_where_it_is(dispatch, service, script):
    inbox, sent = await _sent_to_rome(dispatch, service, script)
    [asked] = [e for e in await collect(service.move_dispatched(inbox, sent.id)) if isinstance(e, ApprovalRequired)]
    events = await collect(service.resume(inbox, {asked.interrupt_id: {"choices": None}}))
    assert not [e for e in events if isinstance(e, Dispatched)]
    again = await collect(service.send_dispatched(Session("owner", "web", "t1"), sent.id))
    assert isinstance(again[0], Error)


async def test_messages_are_moved_from_the_inbox_once_one_was_sent_on(dispatch, service):
    [nothing] = await collect(service.move_dispatched(await _inbox(service)))
    assert isinstance(nothing, Error)
    side = Session("owner", "web", await service.new_thread("owner"))
    [elsewhere] = await collect(service.move_dispatched(side))
    assert isinstance(elsewhere, Error)


async def test_work_that_ended_in_the_inbox_is_told_where_its_next_message_goes(dispatch, service, script):
    inbox = await _inbox(service)
    await ended.record(service.store, "owner", inbox.thread_id, "task-1", "The build finished.")
    [sent] = [e for e in await collect(service.send(inbox, "what's next?")) if isinstance(e, Dispatched)]
    script.reply("The build is done.")
    await collect(service.send_dispatched(Session("owner", "web", await service.new_thread("owner")), sent.id))
    told = str(script.requests[0][-1].content)
    assert "started in the user's inbox" in told and "The build finished." in told
