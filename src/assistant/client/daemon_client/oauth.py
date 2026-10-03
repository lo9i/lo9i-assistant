from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import SignedIn, SignInError

_ERRORS = {400: SignInError}


class OAuthApi:
    """Finishing a sign-in (an email account, a remote MCP server) with the code the browser came back with."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def finish(self, state: str, code: str) -> SignedIn:
        """The state and code from the address the browser was sent back to. Raises SignInError."""
        body = {"state": state, "code": code}
        return SignedIn(**await self._transport.request("POST", "/oauth/finish", json=body, errors=_ERRORS))
