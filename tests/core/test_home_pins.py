"""Conversations pinned to Home, and Home's Conversations card built from them (core/home/pins.py, conversations.py)."""

import pytest

from assistant.core import conversations
from assistant.core.agent import AssistantService, ConversationError, HomePinError
from assistant.core.config import settings
from assistant.core.conversations import Conversation
from assistant.core.home import sections
from assistant.core.home.conversations import RECENT, shown
from assistant.core.home.model import HomeSection
from assistant.core.home.sections import CONVERSATIONS

OWNER = settings.owner_id


def _conversation(
    thread_id: str, updated: str = "2026-10-22T15:00:00+00:00", inbox: bool = False, archived: bool = False
) -> Conversation:
    return Conversation(
        thread_id=thread_id,
        title=thread_id.upper(),
        started_at=updated,
        updated_at=updated,
        inbox=inbox,
        archived=archived,
    )


async def _listed(service: AssistantService, *threads: str) -> None:
    for i, thread_id in enumerate(threads):
        await conversations.save(service.store, OWNER, _conversation(thread_id, f"2026-10-22T1{i}:00:00+00:00"))


async def _card(service: AssistantService):
    await service.home_refresh.wait(OWNER)
    page = await service.home(OWNER)
    return next(c for c in page.cards if c.section.id == CONVERSATIONS)


async def test_home_has_a_conversations_card_built_in(service):
    titles = [c.section.title for c in (await service.home(OWNER)).cards]
    assert titles[-1] == "Conversations"


async def test_conversations_are_pinned_once_in_the_order_pinned_and_unpinned(service):
    await _listed(service, "a", "b")
    assert await service.pin_to_home(OWNER, "b") == ["b"]
    assert await service.pin_to_home(OWNER, "a") == ["b", "a"]
    assert await service.pin_to_home(OWNER, "b") == ["b", "a"]
    assert await service.unpin_from_home(OWNER, "b") == ["a"]
    assert await service.unpin_from_home(OWNER, "gone") == ["a"]
    assert await service.home_pins(OWNER) == ["a"]


async def test_neither_the_inbox_nor_an_unknown_conversation_is_pinned(service):
    inbox_id = await service.inbox_thread(OWNER)
    await conversations.save(service.store, OWNER, _conversation(inbox_id))
    with pytest.raises(HomePinError):
        await service.pin_to_home(OWNER, inbox_id)
    with pytest.raises(ConversationError):
        await service.pin_to_home(OWNER, "nowhere")
    assert await service.home_pins(OWNER) == []


async def test_a_deleted_conversation_is_unpinned(service):
    await _listed(service, "a", "b")
    await service.pin_to_home(OWNER, "a")
    await service.pin_to_home(OWNER, "b")
    await service.delete_conversation(OWNER, "a")
    assert await service.home_pins(OWNER) == ["b"]


async def test_the_card_shows_the_pinned_conversations_in_their_order(service):
    await _listed(service, "a", "b", "c")
    await service.pin_to_home(OWNER, "c")
    await service.pin_to_home(OWNER, "a")
    result = (await _card(service)).result
    assert result is not None and result.status == "ok"
    assert [i.title for i in result.items] == ["C", "A"]
    assert result.note == ""
    assert result.items[0].date and result.items[0].time


async def test_the_card_shows_the_recent_conversations_while_none_is_pinned_and_says_so(service):
    await _listed(service, "a", "b")
    await service.pin_to_home(OWNER, "a")
    await service.unpin_from_home(OWNER, "a")
    result = (await _card(service)).result
    assert result is not None
    assert [i.title for i in result.items] == ["B", "A"]
    assert result.note.startswith("Recent")


def test_recent_conversations_leave_out_the_inbox_and_archived_ones_and_stop_at_a_few():
    listed = [
        _conversation("inbox", inbox=True),
        _conversation("old", archived=True),
        *(_conversation(f"t{i}") for i in range(RECENT + 2)),
    ]
    found, pinned = shown(listed, [])
    assert not pinned
    assert [c.thread_id for c in found] == [f"t{i}" for i in range(RECENT)]


def test_pinned_ones_gone_or_the_inbox_are_left_out_and_none_left_falls_back_to_recent():
    listed = [_conversation("inbox", inbox=True), _conversation("a"), _conversation("b")]
    assert [c.thread_id for c in shown(listed, ["gone", "b", "inbox"])[0]] == ["b"]
    assert shown(listed, ["gone"]) == ([listed[1], listed[2]], False)


async def test_the_card_joins_sections_saved_before_it(service):
    mine = HomeSection(id="news", title="News", prompt="Today's news.")
    record = {"sections": [mine.model_dump()], "coded": [sections.COPILOT]}
    await service.store.aput(sections.namespace(OWNER), "sections", record)
    assert [s.id for s in await sections.load(service.store, OWNER)] == ["news", CONVERSATIONS]


async def test_a_removed_card_is_added_back_by_its_id_with_its_own_text(service):
    mine = HomeSection(id="news", title="News", prompt="Today's news.")
    await service.save_home_sections(OWNER, [mine])
    back = HomeSection(id=CONVERSATIONS, title="Chats", prompt="anything", plugins=["calendar"])
    page = await service.save_home_sections(OWNER, [mine, back])
    added = page.cards[1].section
    assert (added.id, added.title, added.plugins) == (CONVERSATIONS, "Chats", [])
    assert added.prompt.startswith("Built by lo9i")
    assert (await _card(service)).result is not None
