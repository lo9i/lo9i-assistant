"""Search providers, fallback and caching."""

import httpx
import pytest

from assistant.core.config import settings
from assistant.core.internet import service as web_service
from assistant.core.internet.providers import BraveProvider, SearchError
from assistant.core.internet.results import SearchResult
from assistant.core.internet.service import WebService


async def test_brave_needs_a_key(monkeypatch):
    monkeypatch.setattr(settings, "brave_search_api_key", "")
    with pytest.raises(SearchError, match="BRAVE_SEARCH_API_KEY"):
        await BraveProvider().search("q", 3)


async def test_brave_request_and_parsing(monkeypatch):
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), token=request.headers["X-Subscription-Token"])
        return httpx.Response(200, json={"web": {"results": [{"title": "T", "url": "https://t", "description": "D"}]}})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(settings, "brave_search_api_key", "key")
    assert await BraveProvider().search("langgraph", 3) == [SearchResult("T", "https://t", "D")]
    assert seen == {"url": "https://api.search.brave.com/res/v1/web/search?q=langgraph&count=3", "token": "key"}


class _Provider:
    def __init__(self, name, results=None):
        self.name, self.results, self.calls = name, results, 0

    async def search(self, query, limit):
        self.calls += 1
        if self.results is None:
            raise SearchError(f"{self.name} failed")
        return self.results


async def test_fallback_and_cache(monkeypatch):
    primary, fallback = _Provider("brave"), _Provider("metasearch", [SearchResult("T", "u", "s")])
    monkeypatch.setattr(settings, "web_search_backend", "brave")
    monkeypatch.setattr(settings, "web_search_fallback", "metasearch")
    monkeypatch.setattr(web_service, "build_provider", {"brave": primary, "metasearch": fallback}.get)
    web = WebService()
    first = await web.search("q", 3)
    assert first.provider == "metasearch" and "brave failed" in first.note
    await web.search(" Q ", 3)
    assert (primary.calls, fallback.calls) == (1, 1)


@pytest.mark.live
async def test_live_metasearch_returns_results():
    outcome = await WebService().search("langgraph sqlite checkpointer", 3)
    assert outcome.results and outcome.results[0].url.startswith("http")


@pytest.mark.live
async def test_live_render_of_a_javascript_page(monkeypatch):
    from assistant.core.internet import browser

    if not browser.installed():
        pytest.skip("headless browser not installed")
    monkeypatch.setattr(settings, "web_render", True)
    text = await WebService().extract("https://quotes.toscrape.com/js/")
    assert "Einstein" in text
