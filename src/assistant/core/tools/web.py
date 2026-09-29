"""Web tools: search the web and read pages. Backends live in core/web/."""

from langchain_core.tools import tool

from assistant.core.tools.registry import register
from assistant.core.web.fetch import FetchError
from assistant.core.web.policy import BlockedDomain
from assistant.core.web.providers import SearchError
from assistant.core.web.service import SearchOutcome, WebService
from assistant.core.web.url_safety import UnsafeUrl

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
    except (FetchError, UnsafeUrl, BlockedDomain) as e:
        return f"Could not read {url}: {e}"


def _format(outcome: SearchOutcome) -> str:
    if not outcome.results:
        return f"No results ({outcome.provider})."
    lines = [f"Results from {outcome.provider}" + (f" ({outcome.note})" if outcome.note else "") + ":"]
    for i, r in enumerate(outcome.results, 1):
        lines.append(f"{i}. {r.title}\n   {r.url}\n   {r.snippet}")
    return "\n".join(lines)
