"""Search services with free endpoints that need no key: Exa and Parallel (MCP servers) and Keenable
(an HTTP API). Tried after the public engines, so search keeps working without a key when those
block this computer. The query goes to each service as is; no user identifier is sent."""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, ClassVar

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation, TextContent

from assistant.core.internet.providers import SearchError
from assistant.core.internet.results import SearchResult

_TIMEOUT = 20
# Exa and Parallel return long excerpts; a search result needs only a snippet.
_SNIPPET_CHARS = 300
_CLIENT = Implementation(name="lo9i", version="1")


class ExaProvider:
    name = "exa"
    _URL = "https://mcp.exa.ai/mcp"

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        text = await _mcp_text(self.name, self._URL, "web_search_exa", {"query": query, "numResults": limit})
        return [r for block in text.split("\n---\n") if (r := _exa_result(block))][:limit]


class ParallelProvider:
    name = "parallel"
    _URL = "https://search.parallel.ai/mcp"

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        arguments = {"objective": query, "search_queries": [query]}
        text = await _mcp_text(self.name, self._URL, "web_search", arguments)
        try:
            rows = json.loads(text).get("results") or []
        except (ValueError, AttributeError) as e:
            raise SearchError(f"parallel: unexpected answer: {e}") from e
        return [_result(r.get("title", ""), r.get("url", ""), " ".join(r.get("excerpts") or [])) for r in rows[:limit]]


class KeenableProvider:
    name = "keenable"
    _URL = "https://api.keenable.ai/v1/search/public"
    # The public endpoint requires an app name.
    _HEADERS: ClassVar[dict[str, str]] = {"X-Keenable-Title": "lo9i"}

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    self._URL, json={"query": query, "max_results": limit}, headers=self._HEADERS
                )
                response.raise_for_status()
                rows = response.json().get("results") or []
        except (httpx.HTTPError, ValueError, AttributeError) as e:
            raise SearchError(f"keenable: {e}") from e
        return [
            _result(r.get("title", ""), r.get("url", ""), r.get("snippet") or r.get("description", ""))
            for r in rows[:limit]
        ]


async def _mcp_text(name: str, url: str, tool: str, arguments: dict[str, Any]) -> str:
    """The text a tool of a remote MCP server answers. Raises SearchError."""
    try:
        async with asyncio.timeout(_TIMEOUT), Client(_transport(url), client_info=_CLIENT) as client:
            result = await client.call_tool(tool, arguments)
    except Exception as e:  # the MCP client raises transport, protocol and task group errors alike
        raise SearchError(f"{name}: {e}") from e
    text = "\n".join(block.text for block in result.content if isinstance(block, TextContent))
    if result.is_error:
        raise SearchError(f"{name}: {text[:200]}")
    return text


@asynccontextmanager
async def _transport(url: str) -> AsyncIterator:
    async with httpx2.AsyncClient(timeout=_TIMEOUT) as http, streamable_http_client(url, http_client=http) as streams:
        yield streams


def _exa_result(block: str) -> SearchResult | None:
    """One `Title:` / `URL:` / `Highlights:` block of Exa's answer."""
    fields = dict(re.findall(r"^(Title|URL): *(.*)$", block, re.MULTILINE))
    if not fields.get("URL"):
        return None
    _, _, highlights = block.partition("Highlights:")
    return _result(fields.get("Title", ""), fields["URL"], highlights)


def _result(title: str, url: str, text: str) -> SearchResult:
    snippet = " ".join(text.split())
    if len(snippet) > _SNIPPET_CHARS:
        snippet = snippet[:_SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"
    return SearchResult(title.strip(), url.strip(), snippet)
