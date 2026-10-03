"""Signing in to a remote MCP server: a connection whose OAuth flow waits for the browser.

The connection runs in its own task. It stops at the authorization page, which goes to the client
that asked, and waits there until the web app's /app/oauth page brings the code back (`finish`). The
SDK then trades the code for tokens and the connection lists the tools, proving the sign-in works.
"""

import asyncio
import contextlib
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
from mcp.client.session import IncomingMessage

from assistant.core.mcp.connection import ClientFactory, describe, list_tools
from assistant.core.mcp.oauth import McpAuth
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.oauth import PENDING_SECONDS, SignInError, expiry

# Discovering the authorization server and registering with it.
_PAGE_SECONDS = 60


@dataclass
class McpSignIn:
    server: str
    # The authorization page to open in a browser.
    page: str
    expires_at: float
    _code: asyncio.Future[AuthorizationCodeResult]
    _connecting: asyncio.Task[None]

    @property
    def state(self) -> str:
        return parse_qs(urlparse(self.page).query).get("state", [""])[0]

    async def finish(self, code: str) -> None:
        """Hand over the code and wait until the server accepted it. Raises SignInError."""
        if self._code.done() or self._connecting.done():
            raise SignInError(f"This sign-in to {self.server} has expired or was replaced. Start it again.")
        self._code.set_result(AuthorizationCodeResult(code=code, state=self.state))
        try:
            await self._connecting
        except asyncio.CancelledError:
            if (task := asyncio.current_task()) and task.cancelling():
                raise
            raise SignInError(f"A newer sign-in to {self.server} replaced this one.") from None
        except Exception as e:
            raise SignInError(f"Couldn't sign in to {self.server}: {describe(e)}") from e

    def cancel(self) -> None:
        self._connecting.cancel()


async def start(server: McpServer, auth: McpAuth, redirect_uri: str, factory: ClientFactory) -> McpSignIn:
    """Raises McpServerError when the server can't be reached or doesn't ask to sign in."""
    loop = asyncio.get_running_loop()
    page: asyncio.Future[str] = loop.create_future()
    code: asyncio.Future[AuthorizationCodeResult] = loop.create_future()

    async def show_page(url: str) -> None:
        page.set_result(url)

    async def wait_for_code() -> AuthorizationCodeResult:
        return await asyncio.wait_for(code, PENDING_SECONDS)

    provider = auth.for_sign_in(server, redirect_uri, show_page, wait_for_code)
    connecting = asyncio.create_task(_connect(server, provider, auth, factory))
    connecting.add_done_callback(_consume)
    await asyncio.wait([page, connecting], timeout=_PAGE_SECONDS, return_when=asyncio.FIRST_COMPLETED)
    if page.done():
        return McpSignIn(server.name, page.result(), expiry(), code, connecting)
    reason = _no_page(server.name, connecting)
    connecting.cancel()
    raise McpServerError(reason)


async def _connect(server: McpServer, provider: OAuthClientProvider, auth: McpAuth, factory: ClientFactory) -> None:
    async with factory(server, _ignore, provider) as client:
        await list_tools(client)
    await auth.remember(server.name, provider)


def _no_page(name: str, connecting: asyncio.Task[None]) -> str:
    if not connecting.done():
        return f"{name} didn't answer within {_PAGE_SECONDS}s."
    error = connecting.exception()
    if error is None:
        return f"{name} doesn't ask to sign in: it connects without it."
    return f"Couldn't sign in to {name}: {describe(error)}"


def _consume(task: asyncio.Task[None]) -> None:
    """A sign-in nobody finishes ends in an error that nobody awaits."""
    if not task.cancelled():
        with contextlib.suppress(Exception):
            task.exception()


async def _ignore(message: IncomingMessage) -> None:
    pass
