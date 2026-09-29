"""Web search and extraction with caching and a fallback search provider."""

import asyncio
from dataclasses import dataclass

from assistant.core.config import settings
from assistant.core.web.cache import TtlCache
from assistant.core.web.fetch import fetch_page
from assistant.core.web.providers import SearchError, SearchProvider, build_provider
from assistant.core.web.results import SearchResult
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
            page = await fetch_page(url)
            cached = await asyncio.to_thread(fit, page)
            self._pages.put(url, cached)
        return cached

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
