"""Signing in to Google and Microsoft mail with OAuth: the authorization code flow with PKCE, then
XOAUTH2 with an access token where other accounts use a password.

The user registers their own OAuth app (a shared one would need Google's paid review for mail
scopes) and gives its client id and secret. The provider sends the browser back to the web app's
/app/oauth page, which hands the code to the daemon with the one-time `state`. The refresh token is
the account's secret, encrypted like a password; access tokens are refreshed when they expire.
"""

import base64
import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlencode

import httpx

from assistant.core.integrations.email.errors import EmailError

_TIMEOUT = 20
# A sign-in not finished in this time is forgotten.
_PENDING_SECONDS = 600
# Refreshed this long before it expires, so a token never runs out mid-connection.
_MARGIN_SECONDS = 120


@dataclass(frozen=True)
class OAuthProvider:
    id: str
    name: str
    auth_url: str
    token_url: str
    scopes: str
    smtp_host: str
    smtp_port: int
    imap_host: str
    # Extra parameters for the sign-in page (Google returns a refresh token only when asked).
    extra: tuple[tuple[str, str], ...] = ()


PROVIDERS = {
    "google": OAuthProvider(
        "google",
        "Google",
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "https://mail.google.com/",
        "smtp.gmail.com",
        587,
        "imap.gmail.com",
        (("access_type", "offline"), ("prompt", "consent")),
    ),
    "microsoft": OAuthProvider(
        "microsoft",
        "Microsoft",
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send offline_access",
        "smtp.office365.com",
        587,
        "outlook.office365.com",
        (("prompt", "select_account"),),
    ),
}


@dataclass
class Tokens:
    """An account's OAuth sign-in, kept as its secret."""

    provider: str
    client_id: str
    client_secret: str
    refresh_token: str
    access_token: str = ""
    expires_at: float = 0

    def to_secret(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_secret(cls, text: str) -> "Tokens":
        return cls(**json.loads(text))

    def expired(self, now: float) -> bool:
        return now >= self.expires_at - _MARGIN_SECONDS


@dataclass(frozen=True)
class SignIn:
    """A sign-in waiting for the provider to send the browser back."""

    provider: str
    client_id: str
    client_secret: str
    redirect_uri: str
    verifier: str
    address: str
    label: str
    # Signing an existing account in again; "" for a new one.
    account_id: str
    expires_at: float


class SignIns:
    """Sign-ins in progress, by their one-time `state`. Kept in memory: a restart only means
    signing in again."""

    def __init__(self) -> None:
        self._pending: dict[str, SignIn] = {}

    def start(self, sign_in: SignIn) -> str:
        """The provider's sign-in page for it."""
        provider = provider_for(sign_in.provider)
        state = secrets.token_urlsafe(32)
        self._forget_expired(time.time())
        self._pending[state] = sign_in
        query = {
            "client_id": sign_in.client_id,
            "response_type": "code",
            "redirect_uri": sign_in.redirect_uri,
            "scope": provider.scopes,
            "state": state,
            "code_challenge": _challenge(sign_in.verifier),
            "code_challenge_method": "S256",
            "login_hint": sign_in.address,
            **dict(provider.extra),
        }
        return f"{provider.auth_url}?{urlencode(query)}"

    def take(self, state: str) -> SignIn:
        """The sign-in for this state, once. Raises EmailError for an unknown or expired one."""
        sign_in = self._pending.pop(state, None)
        if sign_in is None or time.time() > sign_in.expires_at:
            raise EmailError("This sign-in has expired or was already used. Start it again from the app.")
        return sign_in

    def _forget_expired(self, now: float) -> None:
        self._pending = {s: p for s, p in self._pending.items() if p.expires_at > now}


def new_sign_in(
    provider: str, client_id: str, client_secret: str, redirect_uri: str, address: str, label: str, account_id: str
) -> SignIn:
    """Raises EmailError for an unknown provider or missing values."""
    provider_for(provider)
    if not client_id.strip() or not redirect_uri.strip() or "@" not in address:
        raise EmailError("Enter the email address and your OAuth app's client ID.")
    verifier = secrets.token_urlsafe(64)
    expires = time.time() + _PENDING_SECONDS
    return SignIn(
        provider,
        client_id.strip(),
        client_secret.strip(),
        redirect_uri,
        verifier,
        address.strip(),
        label,
        account_id,
        expires,
    )


async def exchange(sign_in: SignIn, code: str) -> Tokens:
    """The tokens for a code the provider sent back. Raises EmailError."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": sign_in.redirect_uri,
        "code_verifier": sign_in.verifier,
    }
    answer = await _token_request(sign_in.provider, sign_in.client_id, sign_in.client_secret, data)
    if not answer.get("refresh_token"):
        raise EmailError(f"{provider_for(sign_in.provider).name} gave no refresh token; sign in again.")
    tokens = Tokens(sign_in.provider, sign_in.client_id, sign_in.client_secret, answer["refresh_token"])
    return _with_access(tokens, answer)


async def refresh(tokens: Tokens) -> Tokens:
    """A new access token. Raises EmailError when the provider refuses (revoked, expired)."""
    data = {"grant_type": "refresh_token", "refresh_token": tokens.refresh_token}
    answer = await _token_request(tokens.provider, tokens.client_id, tokens.client_secret, data)
    # Microsoft sends a new refresh token each time; Google keeps the old one.
    tokens.refresh_token = answer.get("refresh_token") or tokens.refresh_token
    return _with_access(tokens, answer)


def provider_for(provider_id: str) -> OAuthProvider:
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise EmailError(f"Signing in with {provider_id} isn't supported: Google or Microsoft.")
    return provider


async def _token_request(provider_id: str, client_id: str, client_secret: str, data: dict[str, str]) -> dict:
    provider = provider_for(provider_id)
    form = {**data, "client_id": client_id, **({"client_secret": client_secret} if client_secret else {})}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            response = await http.post(provider.token_url, data=form)
    except httpx.HTTPError as e:
        raise EmailError(f"Couldn't reach {provider.name} to sign in: {e}") from e
    answer = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code != 200 or "access_token" not in answer:
        reason = answer.get("error_description") or answer.get("error") or f"HTTP {response.status_code}"
        raise EmailError(f"{provider.name} refused the sign-in: {reason}")
    return answer


def _with_access(tokens: Tokens, answer: dict) -> Tokens:
    tokens.access_token = answer["access_token"]
    tokens.expires_at = time.time() + float(answer.get("expires_in", 3600))
    return tokens


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
