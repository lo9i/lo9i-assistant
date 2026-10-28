from assistant.core import conversations
from assistant.core.conversation.dispatch import QUICK, Pick
from assistant.core.conversations import Conversation


async def _side(service, thread_id: str, title: str, tags: list[str]) -> None:
    record = Conversation(thread_id, title, "2026-10-01T10:00:00+00:00", "2026-10-01T10:00:00+00:00", tags=tags)
    await conversations.save(service.store, "owner", record)


async def test_a_first_message_goes_on_in_the_conversation_it_continues_when_the_pick_is_sure(dispatch, service):
    await _side(service, "t1", "Trip to Rome", ["rome"])
    dispatch.picks.append(Pick("t1", 0.95, ""))
    assert await service.route_first_message("owner", "book the flights to Rome") == "t1"
    message, found = dispatch.inputs[0]
    assert message == "book the flights to Rome" and [c.thread_id for c in found] == ["t1"]


async def test_it_stays_in_the_new_conversation_when_unsure_quick_or_there_is_none(dispatch, service):
    assert await service.route_first_message("owner", "hello") == ""
    assert dispatch.inputs == []  # nothing to pick among: no model call
    await _side(service, "t1", "Trip to Rome", ["rome"])
    dispatch.picks.extend([Pick("t1", 0.5, ""), Pick(QUICK, 1.0, "")])
    assert await service.route_first_message("owner", "what about Rome?") == ""
    assert await service.route_first_message("owner", "what time is it in Rome?") == ""


async def test_the_inbox_is_never_a_pick(dispatch, service):
    inbox = await service.session("owner", "web")
    await _side(service, "t1", "Trip to Rome", ["rome"])
    await service.route_first_message("owner", "Rome")
    assert inbox.thread_id not in [c.thread_id for c in dispatch.inputs[0][1]]
