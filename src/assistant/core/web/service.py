"""Web search and extraction with caching and a fallback search provider."""

import asyncio
from dataclasses import dataclass

from assistant.core.config import settings
from assistant.core.web import browser
from assistant.core.web.cache import TtlCache
from assistant.core.web.fetch import fetch_page
from assistant.core.web.providers import SearchError, SearchProvider, build_provider
from assistant.core.web.results import Page, SearchResult
from assistant.core.web.truncate import fit


@dataclass
class SearchOutcome:
    results: list[SearchResult]
    provider: str
    note: str = ""


class WebService:
    def __init__(self) -> None:
        self._primary = build_provider(settings.web_search_backend)
        self._fallback = _fallback_for(self._primary)
        self._searches = TtlCache()
        self._pages = TtlCache()
        self._renderer = browser.BrowserRenderer()

    async def search(self, query: str, limit: int) -> SearchOutcome:
        key = (query.strip().lower(), limit)
        cached = self._searches.get(key)
        if cached is None:
            cached = await self._search_uncached(query, limit)
            self._searches.put(key, cached)
        return cached

    async def extract(self, url: str) -> str:
        """Page text, shortened when long. Raises FetchError, UnsafeUrl or BlockedDomain."""
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

    async def _search_uncached(self, query: str, limit: int) -> SearchOutcome:
        try:
            return SearchOutcome(await self._primary.search(query, limit), self._primary.name)
        except SearchError as e:
            if self._fallback is None:
                raise
            results = await self._fallback.search(query, limit)
            return SearchOutcome(results, self._fallback.name, note=f"{e}; used {self._fallback.name} instead")


def _fallback_for(primary: SearchProvider) -> SearchProvider | None:
    name = settings.web_search_fallback
    if name == "none" or name == primary.name:
        return None
    return build_provider(name)
