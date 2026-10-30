"""Refreshing Home: every section built again in the background, each on its own, its result saved as it's ready.

A refresh asked for while the last one ended under FRESH_MINUTES ago, the same day, does nothing unless forced
(the Refresh button), so opening Home again and again doesn't call the model each time. The daemon keeps it
current on its own too (schedule.py). One refresh runs per user at a
time; sections the user just changed are built after it."""

import asyncio
import logging
from collections.abc import Callable, Collection, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

import openai
from langgraph.store.base import BaseStore

from assistant.core import i18n
from assistant.core.bus import EventBus
from assistant.core.home import results, sections
from assistant.core.home.builder import SectionBuilder
from assistant.core.home.clock import within
from assistant.core.home.coded import CodedSection
from assistant.core.home.model import HomeCard, HomePage, HomeSection, SectionResult
from assistant.core.i18n import message, said
from assistant.core.mcp import servers
from assistant.core.mcp.sanitize import tool_name
from assistant.core.mcp.servers import McpServer

logger = logging.getLogger(__name__)

FRESH_MINUTES = 10
# A section that takes longer fails, so a plugin that hangs can't hold Home.
SECTION_SECONDS = 180


class ReadOnlyTools(Protocol):
    """The plugins' tools that only read (core/plugin_tools.py)."""

    def read_only_definitions(self) -> list[dict[str, Any]]: ...


class HomeRefresh:
    def __init__(
        self,
        store: BaseStore,
        bus: EventBus,
        builder: Callable[[], SectionBuilder],
        tools: ReadOnlyTools,
        coded: Mapping[str, CodedSection],
    ) -> None:
        """`builder` gives the section builder of the model in use, which changes when the user picks another.
        `coded`: the sections built by code, by id (coded.py)."""
        self._store = store
        self._bus = bus
        self._builder = builder
        self._tools = tools
        self._coded = coded
        # The refresh running for each user.
        self._running: dict[str, asyncio.Task] = {}

    async def page(self, user_id: str) -> HomePage:
        found = await results.load(self._store, user_id)
        cards = [HomeCard(section=s, result=found.get(s.id)) for s in await sections.load(self._store, user_id)]
        refreshed = await results.refreshed_at(self._store, user_id)
        return HomePage(
            cards=cards, updated_at=refreshed.isoformat() if refreshed else "", refreshing=user_id in self._running
        )

    async def refresh(self, user_id: str, force: bool = False, only: Collection[str] | None = None) -> None:
        """Starts building every section in the background, unless a refresh is running or, unforced, the last one
        ended under FRESH_MINUTES ago, today. The sections in `only` (the ones the user just changed) are built whenever
        it was, once the running refresh ends."""
        if only is None and not force and user_id not in self._running and await self._fresh(user_id):
            return
        # Read after the await, with none between it and starting: a call meanwhile may have started one.
        running = self._running.get(user_id)
        if running is not None and only is None:
            return
        task = asyncio.create_task(self._run(user_id, only, running))
        self._running[user_id] = task
        task.add_done_callback(lambda done: self._ended(user_id, done))
        self._bus.publish("home")

    async def wait(self, user_id: str) -> None:
        """Until no refresh runs, for tests and callers that need the result."""
        while (task := self._running.get(user_id)) is not None:
            await asyncio.wait([task])

    async def _fresh(self, user_id: str) -> bool:
        return within(await results.refreshed_at(self._store, user_id), datetime.now(UTC), FRESH_MINUTES)

    def _ended(self, user_id: str, task: asyncio.Task) -> None:
        if self._running.get(user_id) is task:
            del self._running[user_id]
        self._bus.publish("home")

    async def _run(self, user_id: str, only: Collection[str] | None, after: asyncio.Task | None) -> None:
        if after is not None:
            await asyncio.wait([after])
        wanted = [s for s in await sections.load(self._store, user_id) if only is None or s.id in only]
        installed = [s for s in await servers.load_all(self._store) if s.enabled and s.is_mcp]
        await asyncio.gather(*(self._build(user_id, s, installed) for s in wanted))
        if only is None:
            await results.mark_refreshed(self._store, user_id, datetime.now(UTC))

    async def _build(self, user_id: str, section: HomeSection, installed: list[McpServer]) -> None:
        """Never raises: a section that fails says so and keeps the items it had."""
        now = datetime.now(UTC)
        tools = _tools_of(section, self._tools.read_only_definitions())
        if (coded := self._coded.get(section.id)) is not None:
            result = await self._built_by_code(user_id, section, coded, now)
        elif not tools:
            result = _unavailable(section, installed, now)
        else:
            result = await self._built(user_id, section, tools, now, _page(section, installed))
        await results.save(self._store, user_id, await self._in_language(result))

    async def _built(
        self, user_id: str, section: HomeSection, tools: list[dict[str, Any]], now: datetime, page: str
    ) -> SectionResult:
        try:
            async with asyncio.timeout(SECTION_SECONDS):
                content = await self._builder().build(user_id, section, tools, now)
        except Exception as e:
            if _expected(e):  # a model limit or outage, not a fault: kept out of the health check
                logger.info("Couldn't build the Home section %s: %s", section.title, e)
            else:
                logger.warning("Couldn't build the Home section %s: %s", section.title, e, exc_info=True)
            return await self._failed(user_id, section, _reason(e), now, page)
        return SectionResult(
            section_id=section.id,
            title=section.title,
            status="ok",
            items=content.items,
            note=content.note,
            page=page,
            at=now.isoformat(),
        )

    async def _built_by_code(
        self, user_id: str, section: HomeSection, coded: CodedSection, now: datetime
    ) -> SectionResult:
        try:
            content = await coded.build()
        except Exception as e:
            logger.warning("Couldn't build the Home section %s: %s", section.title, e, exc_info=True)
            return await self._failed(user_id, section, _reason(e), now, "")
        return SectionResult(
            section_id=section.id,
            title=section.title,
            status="ok",
            items=content.items,
            note=content.note,
            at=now.isoformat(),
        )

    async def _in_language(self, result: SectionResult) -> SectionResult:
        """Why it failed, kept in the language chosen."""
        return result.model_copy(update={"error": (await i18n.chosen(self._store)).shown(result.error)})

    async def _failed(self, user_id: str, section: HomeSection, error: str, now: datetime, page: str) -> SectionResult:
        """Keeping the items it had, which Home still shows."""
        last = (await results.load(self._store, user_id)).get(section.id)
        return SectionResult(
            section_id=section.id,
            title=section.title,
            status="failed",
            items=last.items if last else [],
            error=error,
            page=page,
            at=now.isoformat(),
        )


def _tools_of(section: HomeSection, definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The read-only tools of the section's plugins, or of every plugin when it names none."""
    if not section.plugins:
        return definitions
    prefixes = tuple(tool_name(p, "") for p in section.plugins)
    return [d for d in definitions if d["function"]["name"].startswith(prefixes)]


def _page(section: HomeSection, installed: list[McpServer]) -> str:
    """The first of its plugins that comes with a web page."""
    with_page = {s.name for s in installed if s.page_command}
    return next((p for p in section.plugins if p in with_page), "")


def _unavailable(section: HomeSection, installed: list[McpServer], now: datetime) -> SectionResult:
    names = {s.name for s in installed}
    missing = [p for p in section.plugins if p not in names]
    if missing:
        error = said("Needs the {plugins} plugin: install it or turn it on in Plugins.", plugins=", ".join(missing))
    elif section.plugins:
        error = said("{plugins} has no tools that only read, or isn't connected.", plugins=", ".join(section.plugins))
    else:
        error = said("No plugin with tools that only read is installed.")
    return SectionResult(
        section_id=section.id, title=section.title, status="unavailable", error=error, at=now.isoformat()
    )


_UNREACHABLE = (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError)


def _expected(error: Exception) -> bool:
    """Model limits and outages, which need no traceback in the log."""
    cause = error.__cause__ or error
    return isinstance(error, TimeoutError) or isinstance(cause, (openai.RateLimitError, *_UNREACHABLE))


def _reason(error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return said("It took more than {minutes} minutes.", minutes=SECTION_SECONDS // 60)
    cause = error.__cause__ or error
    if isinstance(cause, openai.RateLimitError):
        return said("The model's usage limit was reached; it will try again on the next refresh.")
    if isinstance(cause, _UNREACHABLE):
        return said("The model couldn't be reached; it will try again on the next refresh.")
    text = message(error).strip() or type(error).__name__
    return text if len(text) <= 300 else text[:300] + "…"
