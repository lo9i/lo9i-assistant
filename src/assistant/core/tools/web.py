"""Web tools: search the web and read pages. Backends live in core/internet/."""

from langchain_core.tools import tool

from assistant.core.internet.fetch import FetchError
from assistant.core.internet.policy import BlockedDomainError
from assistant.core.internet.providers import SearchError
from assistant.core.internet.service import SearchOutcome, WebService
from assistant.core.internet.url_safety import UnsafeUrlError
from assistant.core.tools.registry import register

_MAX_RESULTS = 10
# Holds the search and page caches for this process.
_web = WebService()


@register("web")
@tool
async def web_search(query: str, limit: int = 5) -> str:
    """Search the web. Returns titles, URLs and short snippets. Use web_extract to read a result."""
    try:
        outcome = await _web.search(query, max(1, min(limit, _MAX_RESULTS)))
    except SearchError as e:
        return f"Search failed: {e}"
    return _format(outcome)


@register("web")
@tool
async def web_extract(url: str) -> str:
    """Read a web page as text. Long pages are shortened; the full text is saved in the workspace."""
    try:
        return await _web.extract(url)
    except (FetchError, UnsafeUrlError, BlockedDomainError) as e:
        return f"Could not read {url}: {e}"


def _format(outcome: SearchOutcome) -> str:
    if not outcome.results:
        return f"No results ({outcome.provider})."
    lines = [f"Results from {outcome.provider}" + (f" ({outcome.note})" if outcome.note else "") + ":"]
    for i, r in enumerate(outcome.results, 1):
        lines.append(f"{i}. {r.title}\n   {r.url}\n   {r.snippet}")
    return "\n".join(lines)
