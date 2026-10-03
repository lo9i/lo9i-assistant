"""Search providers, fallback and caching."""

import httpx
import pytest

from assistant.core.config import settings
from assistant.core.internet.keyless import ExaProvider, KeenableProvider, ParallelProvider
from assistant.core.internet.providers import BraveProvider, SearchError
from assistant.core.internet.results import SearchResult
from assistant.core.internet.service import WebService


async def test_brave_request_and_parsing(monkeypatch):
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), token=request.headers["X-Subscription-Token"])
        return httpx.Response(200, json={"web": {"results": [{"title": "T", "url": "https://t", "description": "D"}]}})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    assert await BraveProvider("key").search("langgraph", 3) == [SearchResult("T", "https://t", "D")]
    assert seen == {"url": "https://api.search.brave.com/res/v1/web/search?q=langgraph&count=3", "token": "key"}


class _Provider:
    def __init__(self, name, results=None):
        self.name, self.results, self.calls = name, results, 0

    async def search(self, query, limit):
        self.calls += 1
        if self.results is None:
            raise SearchError(f"{self.name} failed")
        return self.results


_HIT = [SearchResult("T", "u", "s")]


async def test_without_a_key_the_first_keyless_provider_that_answers():
    metasearch, exa, brave = _Provider("metasearch", []), _Provider("exa", _HIT), _Provider("brave")
    outcome = await WebService([metasearch, exa], lambda key: brave).search("q", 3)
    assert (outcome.provider, outcome.note) == ("exa", "metasearch: no results")
    assert brave.calls == 0


async def test_brave_first_with_a_key():
    metasearch, brave = _Provider("metasearch"), _Provider("brave", [SearchResult("B", "u", "s")])
    keys = []
    web = WebService([metasearch], lambda key: keys.append(key) or brave)
    assert (await web.search("q", 3, "key")).provider == "brave"
    assert keys == ["key"] and metasearch.calls == 0


async def test_fallback_when_brave_fails_and_cache():
    metasearch, brave = _Provider("metasearch", _HIT), _Provider("brave")
    web = WebService([metasearch], lambda key: brave)
    first = await web.search("q", 3, "key")
    assert first.provider == "metasearch" and first.note == "brave failed"
    await web.search(" Q ", 3, "key")
    assert (brave.calls, metasearch.calls) == (1, 1)


async def test_every_provider_failing_is_reported():
    web = WebService([_Provider("metasearch"), _Provider("exa", [])])
    with pytest.raises(SearchError, match="metasearch failed; exa: no results"):
        await web.search("q", 3)


@pytest.mark.live
async def test_live_metasearch_returns_results():
    outcome = await WebService().search("langgraph sqlite checkpointer", 3)
    assert outcome.results and outcome.results[0].url.startswith("http")


@pytest.mark.live
@pytest.mark.parametrize("provider", [ExaProvider(), ParallelProvider(), KeenableProvider()], ids=lambda p: p.name)
async def test_live_keyless_provider_returns_results(provider):
    results = await provider.search("python asyncio timeout", 3)
    assert 0 < len(results) <= 3 and results[0].url.startswith("http") and results[0].title


@pytest.mark.live
async def test_live_render_of_a_javascript_page(monkeypatch):
    from assistant.core.internet import browser

    if not browser.installed():
        pytest.skip("headless browser not installed")
    monkeypatch.setattr(settings, "web_render", True)
    text = await WebService().extract("https://quotes.toscrape.com/js/")
    assert "Einstein" in text
