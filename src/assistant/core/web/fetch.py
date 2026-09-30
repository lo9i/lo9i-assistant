"""Downloads a page and turns it into text. Every redirect hop passes the same checks."""

import asyncio
import re

import httpx
import trafilatura

from assistant.core.web.policy import check_allowed
from assistant.core.web.results import Page
from assistant.core.web.url_safety import check_url

_TIMEOUT = 20
_MAX_REDIRECTS = 5
_MAX_BYTES = 5_000_000
_USER_AGENT = "Mozilla/5.0 (compatible; lo9i-assistant/0.1)"
_TEXT_TYPES = ("text/plain", "text/markdown", "application/json", "text/csv")


class FetchError(Exception):
    pass


async def fetch_page(url: str) -> Page:
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False, headers={"User-Agent": _USER_AGENT}) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            check_allowed(url)
            await check_url(url)
            async with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = str(response.next_request.url)
                    continue
                if response.is_error:
                    raise FetchError(f"HTTP {response.status_code} for {url}")
                return await _to_page(url, response.headers.get("content-type", ""), await _read(response))
    raise FetchError(f"Too many redirects for {url}")


async def _read(response: httpx.Response) -> bytes:
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > _MAX_BYTES:
            break
    return bytes(body[:_MAX_BYTES])


async def _to_page(url: str, content_type: str, body: bytes) -> Page:
    text = body.decode(errors="replace")
    if "html" in content_type:
        return Page(url, _title(text), await asyncio.to_thread(html_to_markdown, text, url))
    if content_type.startswith(_TEXT_TYPES):
        return Page(url, "", text)
    raise FetchError(f"Unsupported content type {content_type or 'unknown'} for {url}")


def html_to_markdown(html: str, url: str) -> str:
    text = trafilatura.extract(html, url=url, output_format="markdown", include_links=True, include_tables=True)
    return text or "(no readable text found on the page)"


def _title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return " ".join(match.group(1).split()) if match else ""
