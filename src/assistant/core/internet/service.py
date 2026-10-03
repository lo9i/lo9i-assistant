"""Web search and extraction with caching. Searches try providers in order until one answers: the
Brave Search API when the user set a key, the public engines, then services with free endpoints
(core/internet/keyless.py)."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from assistant.core.config import settings
from assistant.core.internet import browser
from assistant.core.internet.cache import TtlCache
from assistant.core.internet.fetch import fetch_page
from assistant.core.internet.keyless import ExaProvider, KeenableProvider, ParallelProvider
from assistant.core.internet.providers import BraveProvider, MetasearchProvider, SearchError, SearchProvider
from assistant.core.internet.results import Page, SearchResult
from assistant.core.internet.truncate import fit


@dataclass
class SearchOutcome:
    results: list[SearchResult]
    provider: str
    note: str = ""


class WebService:
    def __init__(
        self,
        keyless: list[SearchProvider] | None = None,
        brave: Callable[[str], SearchProvider] = BraveProvider,
    ) -> None:
        self._keyless = keyless or [MetasearchProvider(), ExaProvider(), ParallelProvider(), KeenableProvider()]
        self._brave = brave
        self._searches = TtlCache()
        self._pages = TtlCache()
        self._renderer = browser.BrowserRenderer()

    async def search(self, query: str, limit: int, brave_key: str = "") -> SearchOutcome:
        """With `brave_key`, Brave first. Raises SearchError when no provider found anything."""
        key = (query.strip().lower(), limit, bool(brave_key))
        cached = self._searches.get(key)
        if cached is None:
            cached = await self._search_uncached(query, limit, brave_key)
            self._searches.put(key, cached)
        return cached

    async def extract(self, url: str) -> str:
        """Page text, shortened when long. Raises FetchError, UnsafeUrlError or BlockedDomainError."""
        cached = self._pages.get(url)
        if cached is None:
            page = await self._render_if_thin(await fetch_page(url))
            cached = await asyncio.to_thread(fit, page)
            self._pages.put(url, cached)
        return cached

    async def _render_if_thin(self, page: Page) -> Page:
        """Pages built by JavaScript download with almost no text; render those in the browser."""
        if not settings.web_render or len(page.text) >= settings.web_render_min_chars or not browser.installed():
            return page
        try:
            rendered = await self._renderer.render(page.url)
        except browser.RenderError:
            return page
        return rendered if len(rendered.text) > len(page.text) else page

    async def _search_uncached(self, query: str, limit: int, brave_key: str) -> SearchOutcome:
        providers = ([self._brave(brave_key)] if brave_key else []) + self._keyless
        failures: list[str] = []
        for provider in providers:
            try:
                results = await provider.search(query, limit)
            except SearchError as e:
                failures.append(str(e))
                continue
            if results:
                return SearchOutcome(results, provider.name, note="; ".join(failures))
            failures.append(f"{provider.name}: no results")
        raise SearchError("; ".join(failures))
