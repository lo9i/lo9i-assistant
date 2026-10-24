"""Routing from the inbox finds conversations by meaning too: each conversation's title, tags, latest summary
and first message are embedded (a fake embedder here, whose vectors come from the words), so an older conversation a
message continues in words its tags don't have is still offered to the model."""

from langchain_core.messages import HumanMessage

from assistant.core import conversations
from assistant.core.agent import AssistantService, Session
from assistant.core.conversation import summaries
from assistant.core.conversation.dispatch import candidates
from assistant.core.conversation.meanings import KIND
from assistant.core.conversations import Conversation
from tests.conftest import collect


async def _side(service: AssistantService, thread_id: str, title: str, day: int, tags: list[str] | None = None):
    at = f"2026-09-{day:02d}T10:00:00+00:00"
    await conversations.save(service.store, "owner", Conversation(thread_id, title, at, at, tags=tags or []))


async def _keys(service: AssistantService) -> set[str]:
    return {key for (kind, key) in await service._storage.vectors.indexed("owner") if kind == KIND}


async def test_an_old_conversation_close_in_meaning_is_offered_though_neither_its_tags_nor_recency_bring_it(
    service: AssistantService,
):
    inbox: Session = await service.session("owner", "web")
    await _side(service, "bread", "Sourdough starter feeding schedule", 1, ["baking"])
    for day in range(2, 22):
        await _side(service, f"other{day}", f"Errand number {day}", day)
    await service.conversation_index.sync("owner")
    message = "my sourdough starter smells sour, should I feed it more?"
    without = await candidates(service.store, service._storage.search, "owner", inbox.thread_id, message)
    assert "bread" not in [c.thread_id for c in without]
    found = await candidates(
        service.store, service._storage.search, "owner", inbox.thread_id, message, service._similar
    )
    assert found[0].thread_id == "bread" and len(found) == 15


async def test_what_a_conversation_is_about_includes_how_it_began(service: AssistantService):
    await _side(service, "tap", "New conversation", 1)
    await _side(service, "tax", "New conversation", 2)
    await service._storage.search.add("owner", "tap", [HumanMessage("the kitchen tap drips at night")])
    await service._storage.search.add("owner", "tax", [HumanMessage("file the yearly tax return")])
    await service.conversation_index.sync("owner")
    assert await service._similar.nearest("owner", "the kitchen tap still drips", ["tap", "tax"], 1) == ["tap"]
    assert await service._similar.nearest("owner", "yearly tax return due", ["tap", "tax"], 1) == ["tax"]


async def test_a_conversation_is_found_by_what_its_latest_summary_says_it_moved_on_to(service: AssistantService):
    await _side(service, "move", "New conversation", 1)
    await _side(service, "cake", "New conversation", 2)
    await service._storage.search.add("owner", "move", [HumanMessage("which boxes for the move")])
    await service._storage.search.add("owner", "cake", [HumanMessage("a birthday cake for friday")])
    await service.conversation_index.sync("owner")
    asked = "piano mover on friday"
    assert await service._similar.nearest("owner", asked, ["move", "cake"], 1) == ["cake"]
    await summaries.save(service.store, "owner", "move", "After the boxes, they booked a piano mover for Friday.")
    assert await service.conversation_index.sync("owner") == 1  # embedded again with it
    assert await service._similar.nearest("owner", asked, ["move", "cake"], 1) == ["move"]


async def test_a_retitled_conversation_is_embedded_again_and_a_deleted_one_forgotten(service: AssistantService):
    await _side(service, "t1", "Trip", 1)
    await _side(service, "t2", "Taxes", 2)
    assert await service.conversation_index.sync("owner") == 2
    before = await _keys(service)
    assert await service.conversation_index.sync("owner") == 0
    await conversations.set_title(service.store, "owner", "t1", "Trip to Rome in May", ["rome"])
    await conversations.remove(service.store, "owner", "t2")
    assert await service.conversation_index.sync("owner") == 1
    after = await _keys(service)
    assert len(after) == 1 and after.isdisjoint(before) and next(iter(after)).startswith("t1#")


async def test_archived_conversations_are_never_found(service: AssistantService):
    await _side(service, "t1", "Home", 1)
    await conversations.archive(service.store, "owner", "t1", "Home (before the inbox)")
    assert await service.conversation_index.sync("owner") == 0


async def test_without_vectors_or_with_the_model_failing_routing_goes_on_without_meaning(service, embedder):
    await _side(service, "t1", "Sourdough", 1)
    assert await service._similar.nearest("owner", "sourdough", ["t1"], 3) == []
    await service.conversation_index.sync("owner")
    embedder.failing = True
    assert await service._similar.nearest("owner", "sourdough", ["t1"], 3) == []
    inbox = await service.session("owner", "web")
    found = await candidates(service.store, service._storage.search, "owner", inbox.thread_id, "x", service._similar)
    assert [c.thread_id for c in found] == ["t1"]


async def test_a_message_in_the_inbox_is_routed_with_the_conversations_close_in_meaning(dispatch, service):
    await _side(service, "bread", "Sourdough starter feeding schedule", 1, ["baking"])
    for day in range(2, 22):
        await _side(service, f"other{day}", f"Errand number {day}", day)
    await service.conversation_index.sync("owner")
    await collect(service.send(await service.session("owner", "web"), "my sourdough starter smells sour"))
    _, offered = dispatch.inputs[-1]
    assert offered[0].thread_id == "bread"
