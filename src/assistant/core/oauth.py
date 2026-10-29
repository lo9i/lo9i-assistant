"""Sign-ins with OAuth waiting for the browser to come back: email accounts, remote MCP servers and plugins that
sign in (core/mcp/plugin_oauth.py).

The provider sends the browser back to the web app's /app/oauth page, which posts the code with the
one-time `state` to the daemon. The state is the proof, so the page works in a browser that isn't
paired. Kept in memory: a restart only means signing in again.
"""

import base64
import hashlib
import secrets
import time
from typing import Protocol

# A sign-in not finished in this time is forgotten.
PENDING_SECONDS = 600


class SignInError(Exception):
    """A sign-in can't finish: its state is unknown or expired, or the provider refused it."""


class PendingSignIn(Protocol):
    @property
    def expires_at(self) -> float: ...


class SignIns:
    """Sign-ins in progress, by their one-time state."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingSignIn] = {}

    def add(self, state: str, sign_in: PendingSignIn) -> None:
        self._forget_expired(time.time())
        self._pending[state] = sign_in

    def take(self, state: str) -> PendingSignIn:
        """The sign-in for this state, once. Raises SignInError for an unknown or expired one."""
        sign_in = self._pending.pop(state, None)
        if sign_in is None or time.time() > sign_in.expires_at:
            raise SignInError("This sign-in has expired or was already used. Start it again from the app.")
        return sign_in

    def _forget_expired(self, now: float) -> None:
        self._pending = {s: p for s, p in self._pending.items() if p.expires_at > now}


def new_state() -> str:
    return secrets.token_urlsafe(32)


def expiry() -> float:
    """When a sign-in started now is forgotten."""
    return time.time() + PENDING_SECONDS


def challenge(verifier: str) -> str:
    """PKCE's S256 code challenge for a verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
