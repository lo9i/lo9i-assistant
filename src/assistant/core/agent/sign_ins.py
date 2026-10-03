"""Finishing a sign-in (OAuth) when the browser comes back with the code: an email account or a
remote MCP server. The web app's /app/oauth page calls it for both, with the one-time state."""

from dataclasses import dataclass
from typing import Literal

from assistant.core.agent.email import EmailMixin
from assistant.core.agent.mcp import McpMixin
from assistant.core.integrations.email.oauth import SignIn as EmailSignIn
from assistant.core.mcp.sign_in import McpSignIn
from assistant.core.oauth import SignInError

__all__ = ["SignInError", "SignInsMixin", "SignedIn"]


@dataclass
class SignedIn:
    kind: Literal["email", "mcp"]
    # The email account's id, or the MCP server's name.
    id: str
    # What the user knows it by: the address, or the server's name.
    name: str


class SignInsMixin(EmailMixin, McpMixin):
    async def finish_sign_in(self, state: str, code: str) -> SignedIn:
        """Raises SignInError for an unknown or expired state, EmailError or SignInError when the
        provider refuses."""
        pending = self._sign_ins.take(state)
        if isinstance(pending, EmailSignIn):
            account = await self._finish_email_sign_in(pending, code)
            return SignedIn("email", account.id, account.sender)
        if isinstance(pending, McpSignIn):
            server = await self._finish_mcp_sign_in(pending, code)
            return SignedIn("mcp", server.name, server.name)
        raise SignInError("This sign-in can't be finished here.")
