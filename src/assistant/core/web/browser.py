"""Renders JavaScript-heavy pages in headless Chromium (Playwright), for pages whose plain
download has almost no text.

Every request the page makes (navigation, scripts, XHR) passes the same checks as web_extract,
so page JavaScript can't reach private or internal addresses, including the daemon's own API.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from playwright.async_api import Browser, Error as PlaywrightError, Route, async_playwright

from assistant.core.config import settings
from assistant.core.web.fetch import html_to_markdown
from assistant.core.web.policy import BlockedDomain, check_allowed
from assistant.core.web.results import Page
from assistant.core.web.url_safety import UnsafeUrl, check_url

logger = logging.getLogger(__name__)

_RENDER_TIMEOUT_MS = 20_000
_INSTALL_TIMEOUT_SECONDS = 1800
_install_lock = asyncio.Lock()


def _browsers_dir() -> Path:
    return Path(settings.browsers_dir).expanduser()


def installed() -> bool:
    return any(_browsers_dir().glob("chromium_headless_shell-*"))


async def install_browser() -> None:
    """Download the headless shell once (about 100 MB). Safe to call repeatedly."""
    async with _install_lock:
        if installed():
            return
        logger.info("Installing the headless browser for page rendering into %s", _browsers_dir())
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "playwright", "install", "chromium", "--only-shell",
            env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(_browsers_dir())},
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_INSTALL_TIMEOUT_SECONDS)
        if proc.returncode != 0:
            logger.error("Headless browser install failed: %s", stderr.decode(errors="replace")[-500:])


class BrowserRenderer:
    """One browser for the process, started on first use; a fresh context per page."""

    def __init__(self) -> None:
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def render(self, url: str) -> Page:
        browser = await self._get_browser()
        context = await browser.new_context()
        try:
            await context.route("**/*", _guard)
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=_RENDER_TIMEOUT_MS)
            html, title = await page.content(), await page.title()
        finally:
            await context.close()
        return Page(url, title, await asyncio.to_thread(html_to_markdown, html, url))

    async def _get_browser(self) -> Browser:
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_dir())
                playwright = await async_playwright().start()
                self._browser = await playwright.chromium.launch(headless=True)
            return self._browser


async def _guard(route: Route) -> None:
    url = route.request.url
    if url.startswith(("data:", "blob:")):
        await route.continue_()
        return
    try:
        check_allowed(url)
        await check_url(url)
    except (UnsafeUrl, BlockedDomain):
        await route.abort("blockedbyclient")
        return
    await route.continue_()


RenderError = PlaywrightError
