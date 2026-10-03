"""Web tools: search the web and read pages. Backends live in core/internet/."""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.context import Context, require_secrets, require_store
from assistant.core.internet import brave_key
from assistant.core.internet.fetch import FetchError
from assistant.core.internet.policy import BlockedDomainError
from assistant.core.internet.providers import SearchError
from assistant.core.internet.service import SearchOutcome, WebService
from assistant.core.internet.url_safety import UnsafeUrlError
from assistant.core.secret_store import SecretError
from assistant.core.tools.registry import register

_MAX_RESULTS = 10
# Holds the search and page caches for this process.
_web = WebService()


@register("web")
@tool
async def web_search(query: str, runtime: ToolRuntime[Context], limit: int = 5) -> str:
    """Search the web. Returns titles, URLs and short snippets. Use web_extract to read a result."""
    try:
        key = await brave_key.load(require_store(runtime.store), require_secrets(runtime.context))
    except SecretError:
        return "Search failed: the Brave Search API key can't be read. Set it again in the app's web search settings."
    try:
        outcome = await _web.search(query, max(1, min(limit, _MAX_RESULTS)), key)
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
    tried = f" (earlier ones failed: {outcome.note})" if outcome.note else ""
    lines = [f"Results from {outcome.provider}{tried}:"]
    for i, r in enumerate(outcome.results, 1):
        lines.append(f"{i}. {r.title}\n   {r.url}\n   {r.snippet}")
    return "\n".join(lines)
