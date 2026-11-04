"""Home's Open loops card (core/home/loops.py): the open loops but bills due, those due first, built by code, and
built again while a client shows Home when the loops change."""

import asyncio
from datetime import UTC, datetime

from lo9i.core.agent import AssistantService
from lo9i.core.config import settings
from lo9i.core.home import results, sections
from lo9i.core.home.loops import BILL_DUE, LoopsSection
from lo9i.core.proactive import loops
from lo9i.core.proactive.model import LoopDraft

OWNER = settings.owner_id


async def _add(service: AssistantService, text: str, kind: str = "", due: str = "") -> str:
    loop = await loops.add(service.store, OWNER, LoopDraft(text=text, kind=kind, due=due), "assistant")
    assert loop is not None
    return loop.id


async def _titles(service: AssistantService) -> list[str]:
    await service.home_refresh.wait(OWNER)
    page = await service.home(OWNER)
    card = next(c for c in page.cards if c.section.id == sections.LOOPS)
    assert card.section.coded and card.result is not None
    return [i.title for i in card.result.items]


async def test_home_has_an_open_loops_card_built_in(service):
    assert sections.LOOPS in [c.section.id for c in (await service.home(OWNER)).cards]


async def test_the_card_lists_the_open_loops_but_bills_those_due_first(service):
    content = await LoopsSection(service.store, OWNER).build()
    assert (content.items, content.note) == ([], "Nothing open.")
    await _add(service, "Call Ana")
    await _add(service, "Book the flight", due="2026-11-20")
    await _add(service, "Pay the electricity bill", kind=BILL_DUE, due="2026-11-05")
    done = await _add(service, "Send the contract")
    await _add(service, "Renew the passport", due="2026-11-10")
    await loops.close(service.store, OWNER, done, "done")
    content = await LoopsSection(service.store, OWNER).build()
    assert [(i.title, i.date) for i in content.items] == [
        ("Renew the passport", "2026-11-10"),
        ("Book the flight", "2026-11-20"),
        ("Call Ana", ""),
    ]


async def test_while_a_client_shows_home_the_card_is_built_again_when_the_loops_change(service):
    await service.refresh_home(OWNER, force=True)
    assert await _titles(service) == []
    await results.mark_refreshed(service.store, OWNER, datetime.now(UTC))  # no refresh due
    stop = asyncio.Event()
    keeping = asyncio.create_task(service.home_schedule.run(stop))
    await asyncio.sleep(0)
    service.home_schedule.watch("tab-1")
    await _add(service, "Call Ana")
    async with asyncio.timeout(5):
        while await _titles(service) != ["Call Ana"]:
            await asyncio.sleep(0.01)
    stop.set()
    await keeping
