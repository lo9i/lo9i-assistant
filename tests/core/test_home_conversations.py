"""Home's Conversations card, the most recent conversations (core/home/conversations.py)."""

import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from lo9i.core import conversations
from lo9i.core.agent import AssistantService
from lo9i.core.config import settings
from lo9i.core.conversations import Conversation
from lo9i.core.home import results, sections
from lo9i.core.home.conversations import RECENT, shown
from lo9i.core.home.model import HomeSection
from lo9i.core.home.sections import CONVERSATIONS

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


async def _build(service: AssistantService) -> None:
    await service.home_refresh.refresh(OWNER, only=[CONVERSATIONS])


async def _card(service: AssistantService):
    await service.home_refresh.wait(OWNER)
    page = await service.home(OWNER)
    return next(c for c in page.cards if c.section.id == CONVERSATIONS)


async def test_home_has_a_conversations_card_built_in(service):
    titles = [c.section.title for c in (await service.home(OWNER)).cards]
    assert "Conversations" in titles


async def test_the_card_shows_the_recent_conversations_newest_first(service):
    await _listed(service, "a", "b")
    await _build(service)
    result = (await _card(service)).result
    assert result is not None and result.status == "ok"
    assert [i.title for i in result.items] == ["B", "A"]
    assert result.note == ""
    assert result.items[0].date and result.items[0].time


async def _time(service: AssistantService) -> str:
    """The time the card shows for its first conversation."""
    result = (await _card(service)).result
    assert result is not None
    return result.items[0].time


def _local(at: str) -> str:
    return datetime.fromisoformat(at).astimezone(ZoneInfo(settings.timezone)).strftime("%H:%M")


async def test_while_a_client_shows_home_the_card_is_built_again_when_a_conversation_changes(service):
    await _listed(service, "a")
    await _build(service)
    assert await _time(service) == _local("2026-10-22T10:00:00+00:00")
    await results.mark_refreshed(service.store, OWNER, datetime.now(UTC))  # no refresh due
    stop = asyncio.Event()
    keeping = asyncio.create_task(service.home_schedule.run(stop))
    await asyncio.sleep(0)
    await conversations.save(service.store, OWNER, _conversation("a", "2026-10-22T18:30:00+00:00"))
    await asyncio.sleep(0.05)
    assert await _time(service) == _local("2026-10-22T10:00:00+00:00")  # nobody watching
    service.home_schedule.watch("tab-1")
    await conversations.save(service.store, OWNER, _conversation("a", "2026-10-22T19:30:00+00:00"))
    async with asyncio.timeout(5):
        while await _time(service) != _local("2026-10-22T19:30:00+00:00"):
            await asyncio.sleep(0.01)
    stop.set()
    await keeping


def test_recent_conversations_leave_out_the_inbox_and_archived_ones_and_stop_at_a_few():
    listed = [
        _conversation("inbox", inbox=True),
        _conversation("old", archived=True),
        *(_conversation(f"t{i}") for i in range(RECENT + 2)),
    ]
    assert [c.thread_id for c in shown(listed)] == [f"t{i}" for i in range(RECENT)]


async def test_the_card_joins_sections_saved_before_it(service):
    mine = HomeSection(id="news", title="News", prompt="Today's news.")
    record = {"sections": [mine.model_dump()], "coded": [sections.COPILOT]}
    await service.store.aput(sections.namespace(OWNER), "sections", record)
    assert [s.id for s in await sections.load(service.store, OWNER)] == ["news", CONVERSATIONS, sections.LOOPS]


async def test_a_removed_card_is_added_back_by_its_id_with_its_own_text(service):
    mine = HomeSection(id="news", title="News", prompt="Today's news.")
    await service.save_home_sections(OWNER, [mine])
    back = HomeSection(id=CONVERSATIONS, title="Chats", prompt="anything", plugins=["calendar"])
    page = await service.save_home_sections(OWNER, [mine, back])
    added = page.cards[1].section
    assert (added.id, added.title, added.plugins) == (CONVERSATIONS, "Chats", [])
    assert added.prompt.startswith("Built by lo9i")
    assert (await _card(service)).result is not None
