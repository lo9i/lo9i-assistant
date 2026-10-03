"""Web search and page extraction behind swappable providers (used by core/tools/web.py).

- providers: SearchProvider interface; metasearch (public engines via ddgs) and the Brave API.
- fetch: downloads a page and turns it into text.
- url_safety / policy: which URLs may be fetched.
- cache, truncate: result caching and long-page handling.
- service: ties them together.
"""
