"""Answers of the search services with free endpoints, parsed into results."""

import json

import httpx
import pytest

from assistant.core.internet import keyless
from assistant.core.internet.keyless import ExaProvider, KeenableProvider, ParallelProvider
from assistant.core.internet.providers import SearchError
from assistant.core.internet.results import SearchResult

_EXA = (
    """Title: Coroutines and tasks
URL: https://docs.python.org/3/library/asyncio-task.html
Published: N/A
Author: N/A
Highlights:
## Timeouts

asyncio. timeout(delay)
---
Title: No URL here
Highlights:
nothing
---
Title: Second
URL: https://example.com/2
Highlights:
"""
    + "word " * 100
)


def _answering(monkeypatch, text):
    calls = []

    async def mcp_text(name, url, tool, arguments):
        calls.append((name, tool, arguments))
        return text

    monkeypatch.setattr(keyless, "_mcp_text", mcp_text)
    return calls


async def test_exa_blocks_become_results(monkeypatch):
    calls = _answering(monkeypatch, _EXA)
    results = await ExaProvider().search("q", 5)
    assert calls == [("exa", "web_search_exa", {"query": "q", "numResults": 5})]
    assert results[0] == SearchResult(
        "Coroutines and tasks",
        "https://docs.python.org/3/library/asyncio-task.html",
        "## Timeouts asyncio. timeout(delay)",
    )
    assert [r.url for r in results] == ["https://docs.python.org/3/library/asyncio-task.html", "https://example.com/2"]
    assert len(results[1].snippet) <= 301 and results[1].snippet.endswith("…")


async def test_parallel_results_keep_the_limit(monkeypatch):
    rows = [{"url": f"https://p/{i}", "title": f"P{i}", "excerpts": ["a", "b"]} for i in range(5)]
    _answering(monkeypatch, json.dumps({"results": rows}))
    results = await ParallelProvider().search("q", 2)
    assert results == [SearchResult("P0", "https://p/0", "a b"), SearchResult("P1", "https://p/1", "a b")]


async def test_parallel_unexpected_answer(monkeypatch):
    _answering(monkeypatch, "not json")
    with pytest.raises(SearchError, match="parallel"):
        await ParallelProvider().search("q", 2)


async def test_keenable_request_and_errors(monkeypatch):
    seen = {}

    def handler(request):
        seen.update(body=json.loads(request.content), title=request.headers["X-Keenable-Title"])
        if seen["body"]["query"] == "busy":
            return httpx.Response(429)
        return httpx.Response(200, json={"results": [{"title": "K", "url": "https://k", "snippet": "S"}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    assert await KeenableProvider().search("q", 3) == [SearchResult("K", "https://k", "S")]
    assert seen == {"body": {"query": "q", "max_results": 3}, "title": "lo9i"}
    with pytest.raises(SearchError, match=r"keenable.*429"):
        await KeenableProvider().search("busy", 3)
