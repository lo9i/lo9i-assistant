"""Signing in to Google and Microsoft mail with OAuth: the authorization code flow with PKCE, then
XOAUTH2 with an access token where other accounts use a password.

Microsoft signs in with lo9i's own app (`OAuthProvider.built_in_client_id`), a public client: no secret, PKCE only,
so the user types just their address. It sends the browser back only to this computer (a localhost redirect, whose
port Microsoft ignores), so a web app open at another address signs in with it only from localhost. Anyone may give
an app of their own instead (an organization that blocks apps it hasn't approved), with its secret if it has one;
Google always takes the user's own (a shared one would need Google's paid review for mail scopes). The provider sends
the browser back to the web app's /app/oauth page, which hands the code to the daemon with the one-time `state`
(core/oauth.py). The refresh token is the account's secret, encrypted like a password, kept with the app it was
issued to; access tokens are refreshed when they expire, with that app's secret when it has one.
"""

import json
import secrets
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlencode, urlsplit

import httpx

from lo9i.core.i18n import said
from lo9i.core.integrations.email.errors import EmailError
from lo9i.core.oauth import challenge, expiry

_TIMEOUT = 20
# Refreshed this long before it expires, so a token never runs out mid-connection.
_MARGIN_SECONDS = 120
# Where a built-in app may send the browser back: this computer.
_LOCAL_HOSTS = ("localhost", "127.0.0.1")


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
    # lo9i's own app with the provider, signed in with when the user gives none of theirs: a public client (no
    # secret), whose only redirects are on localhost. "" where there's none.
    built_in_client_id: str = ""


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
        built_in_client_id="efc568cc-f1c9-4e57-9229-aeed617aec8c",
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
    # Microsoft's personal-accounts-only endpoint, for Hotmail/Outlook.com/Live addresses.
    personal: bool = False

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
    # The email plugin a new account belongs to (plugins.py).
    plugin: str = ""


def authorization_url(sign_in: SignIn, state: str) -> str:
    """The provider's sign-in page for it."""
    provider = provider_for(sign_in.provider)
    query = {
        "client_id": sign_in.client_id,
        "response_type": "code",
        "redirect_uri": sign_in.redirect_uri,
        "scope": provider.scopes,
        "state": state,
        "code_challenge": challenge(sign_in.verifier),
        "code_challenge_method": "S256",
        "login_hint": sign_in.address,
        **dict(provider.extra),
    }
    return f"{_endpoint(provider.auth_url, personal_address(sign_in.provider, sign_in.address))}?{urlencode(query)}"


# Microsoft's personal domains. Signing these in through /common can land in a work
# organization the address is a guest of; /consumers only takes personal accounts.
_PERSONAL_DOMAINS = ("hotmail.", "outlook.", "live.", "msn.com", "passport.com")


def personal_address(provider: str, address: str) -> bool:
    domain = address.rpartition("@")[2].lower()
    return provider == "microsoft" and domain.startswith(_PERSONAL_DOMAINS)


def _endpoint(url: str, personal: bool) -> str:
    return url.replace("/common/", "/consumers/") if personal else url


def new_sign_in(
    provider: str, client_id: str, client_secret: str, redirect_uri: str, address: str, label: str, account_id: str
) -> SignIn:
    """With the user's own app (`client_id`), else the provider's built-in one. Raises EmailError for an unknown
    provider, missing values, or a built-in app asked to send the browser back somewhere other than this computer."""
    found = provider_for(provider)
    client_id = client_id.strip() or found.built_in_client_id
    if "@" not in address or not redirect_uri.strip():
        raise EmailError(said("Enter the email address."))
    if not client_id:
        raise EmailError(said("Enter your OAuth app's client ID."))
    if client_id == found.built_in_client_id:
        _check_local(found, redirect_uri)
        # A public client: Microsoft refuses a secret from it.
        client_secret = ""
    verifier = secrets.token_urlsafe(64)
    return SignIn(
        provider, client_id, client_secret.strip(), redirect_uri, verifier, address.strip(), label, account_id, expiry()
    )


def local_redirect(redirect_uri: str) -> bool:
    """Whether `redirect_uri` sends the browser back to this computer, the only place a built-in app may."""
    parts = urlsplit(redirect_uri)
    return parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS


def _check_local(provider: OAuthProvider, redirect_uri: str) -> None:
    if not local_redirect(redirect_uri):
        raise EmailError(
            said(
                "lo9i's {name} app can only send you back to lo9i on the computer it runs on. Open lo9i there "
                "(http://localhost) for this step, or use your own {name} app.",
                name=provider.name,
            )
        )


async def exchange(sign_in: SignIn, code: str) -> Tokens:
    """The tokens for a code the provider sent back. Raises EmailError."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": sign_in.redirect_uri,
        "code_verifier": sign_in.verifier,
    }
    personal = personal_address(sign_in.provider, sign_in.address)
    answer = await _token_request(sign_in.provider, sign_in.client_id, sign_in.client_secret, data, personal)
    if not answer.get("refresh_token"):
        raise EmailError(said("{name} gave no refresh token; sign in again.", name=provider_for(sign_in.provider).name))
    tokens = Tokens(
        sign_in.provider, sign_in.client_id, sign_in.client_secret, answer["refresh_token"], personal=personal
    )
    return _with_access(tokens, answer)


async def refresh(tokens: Tokens) -> Tokens:
    """A new access token. Raises EmailError when the provider refuses (revoked, expired)."""
    data = {"grant_type": "refresh_token", "refresh_token": tokens.refresh_token}
    answer = await _token_request(tokens.provider, tokens.client_id, tokens.client_secret, data, tokens.personal)
    # Microsoft sends a new refresh token each time; Google keeps the old one.
    tokens.refresh_token = answer.get("refresh_token") or tokens.refresh_token
    return _with_access(tokens, answer)


def has_built_in(provider_id: str) -> bool:
    """Whether lo9i has an app of its own for `provider_id` ("" for none), so the user needn't register one."""
    provider = PROVIDERS.get(provider_id)
    return provider is not None and bool(provider.built_in_client_id)


def provider_for(provider_id: str) -> OAuthProvider:
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise EmailError(
            said("Signing in with {provider_id} isn't supported: Google or Microsoft.", provider_id=provider_id)
        )
    return provider


async def _token_request(
    provider_id: str, client_id: str, client_secret: str, data: dict[str, str], personal: bool = False
) -> dict:
    provider = provider_for(provider_id)
    form = {**data, "client_id": client_id, **({"client_secret": client_secret} if client_secret else {})}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            response = await http.post(_endpoint(provider.token_url, personal), data=form)
    except httpx.HTTPError as e:
        raise EmailError(said("Couldn't reach {name} to sign in: {error}", name=provider.name, error=e)) from e
    answer = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code != 200 or "access_token" not in answer:
        reason = answer.get("error_description") or answer.get("error") or f"HTTP {response.status_code}"
        raise EmailError(said("{name} refused the sign-in: {reason}", name=provider.name, reason=reason))
    return answer


def _with_access(tokens: Tokens, answer: dict) -> Tokens:
    tokens.access_token = answer["access_token"]
    tokens.expires_at = time.time() + float(answer.get("expires_in", 3600))
    return tokens
