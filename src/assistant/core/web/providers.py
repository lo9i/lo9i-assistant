"""Search providers. Add one by implementing SearchProvider and listing it in `build_provider`."""

import asyncio
import json
import sys
from typing import Protocol

import httpx

from assistant.core.config import settings
from assistant.core.web.results import SearchResult

_TIMEOUT = 15
# Slower engines (Bing) can take over ten seconds.
_METASEARCH_TIMEOUT = 30


class SearchError(Exception):
    """A provider failed; the caller may try the fallback."""


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, limit: int) -> list[SearchResult]: ...


class BraveProvider:
    """The Brave Search API. Needs BRAVE_SEARCH_API_KEY."""

    name = "brave"
    _ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
    _MAX_COUNT = 20

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        if not settings.brave_search_api_key:
            raise SearchError("Brave: BRAVE_SEARCH_API_KEY is not set")
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    self._ENDPOINT,
                    params={"q": query, "count": min(limit, self._MAX_COUNT)},
                    headers={"X-Subscription-Token": settings.brave_search_api_key, "Accept": "application/json"},
                )
                response.raise_for_status()
                rows = response.json().get("web", {}).get("results", [])
        except (httpx.HTTPError, ValueError) as e:
            raise SearchError(f"Brave: {e}") from e
        return [SearchResult(r.get("title", ""), r.get("url", ""), r.get("description", "")) for r in rows[:limit]]


class MetasearchProvider:
    """Queries public search engines (Brave, Bing, Google, ...) through the ddgs library, trying
    the engines in WEB_SEARCH_ENGINES. Runs in a child process: ddgs can block without releasing
    control, and a child process can always be killed on timeout."""

    name = "metasearch"

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "assistant.core.web.ddgs_worker", query, str(limit), settings.web_search_engines,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_METASEARCH_TIMEOUT)
        except TimeoutError as e:
            proc.kill()
            await proc.wait()
            raise SearchError("Search timed out") from e
        if proc.returncode != 0:
            raise SearchError(f"Search failed: {stderr.decode(errors='replace').strip().splitlines()[-1:]}")
        return [SearchResult(**row) for row in json.loads(stdout)]


_PROVIDERS: dict[str, type[SearchProvider]] = {
    "metasearch": MetasearchProvider,
    "brave": BraveProvider,
}


def build_provider(name: str) -> SearchProvider:
    return _PROVIDERS[name]()
