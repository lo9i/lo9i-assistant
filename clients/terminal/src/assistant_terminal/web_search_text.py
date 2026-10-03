"""Web search setup text (Markdown), shared by the setup screen and the plain REPL."""

from assistant.core.agent import WebSearchStatus

_NO_KEY = """## Web search

Searches use public engines and free search services (Exa, Parallel, Keenable), which can block or
limit automated searches. A Brave Search API key makes search reliable:

1. Open https://brave.com/search/api/ and sign up for the free plan.
2. In the dashboard, open **API Keys** and copy the key.
3. Paste it below. It's checked with one search, then kept encrypted on the assistant's computer."""

_KEY_SET = """## Web search

Searches use the Brave Search API. When Brave fails, they use public engines and free search services."""


def describe(status: WebSearchStatus, error: str) -> str:
    text = _KEY_SET if status.brave_key_set else _NO_KEY
    return f"{text}\n\n**{error}**" if error else text
