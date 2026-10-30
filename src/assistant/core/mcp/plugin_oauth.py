"""Plugins that sign in with OAuth: `oauth:` in their server.yaml (format 5) names the provider and the scopes
their processes need. The user signs in from the plugin's setup in the apps with their own OAuth app, as email
does (core/integrations/email/oauth.py): its client ID and secret are typed there, and the provider sends the
browser back to the web app's /app/oauth page (core/oauth.py).

    oauth:
      provider: google
      scopes: [https://www.googleapis.com/auth/drive]

The sign-in is one of the plugin's keys (keys.py), under `ENV`: encrypted, filled in for its processes like its
fields, kept when the plugin is removed and back when it's installed again. Its processes get it in LO9I_OAUTH
as JSON (`Login`): the provider's token endpoint, the client ID and secret, the refresh token and the account
that signed in, so the plugin gets its access tokens itself. It's empty until the user signs in, and again
after they sign out."""

import base64
import json
import secrets
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx
from langgraph.store.base import BaseStore

from assistant.core.i18n import said
from assistant.core.mcp import keys
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.oauth import SignInError, challenge, expiry
from assistant.core.secret_store import SecretBox, SecretError

ENV = "LO9I_OAUTH"
_TIMEOUT = 20


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    auth_url: str
    token_url: str
    # Asked for besides the plugin's scopes, to know which account signed in.
    identity: tuple[str, ...]
    # Extra parameters for the sign-in page (Google returns a refresh token only when asked).
    extra: tuple[tuple[str, str], ...] = ()


PROVIDERS = {
    "google": Provider(
        "google",
        "Google",
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        ("openid", "email"),
        (("access_type", "offline"), ("prompt", "consent")),
    ),
}


@dataclass(frozen=True)
class PluginSignIn:
    """A plugin's sign-in waiting for the provider to send the browser back."""

    plugin: str
    provider: str
    scopes: tuple[str, ...]
    client_id: str
    client_secret: str
    redirect_uri: str
    verifier: str
    expires_at: float


@dataclass(frozen=True)
class Login:
    """What a signed-in plugin's processes get in LO9I_OAUTH."""

    provider: str
    token_url: str
    client_id: str
    client_secret: str
    refresh_token: str
    # The address that signed in; "" when the provider didn't say.
    account: str = ""
    scopes: list[str] = field(default_factory=list)

    def to_env(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_env(cls, text: str) -> "Login | None":
        """None for an empty or unreadable value: not signed in."""
        try:
            data = json.loads(text) if text else None
            return cls(**data) if isinstance(data, dict) else None
        except (ValueError, TypeError):
            return None


def parse(value: object) -> tuple[str, list[str]]:
    """The provider and scopes an `oauth:` section asks for; ("", []) without one. Raises ValueError."""
    if value is None:
        return "", []
    if not isinstance(value, dict):
        raise ValueError(said("its oauth must be a section with a provider and scopes"))
    provider = str(value.get("provider", ""))
    if provider not in PROVIDERS:
        raise ValueError(
            said(
                "its oauth provider {provider!r} isn't one of {providers}",
                provider=provider,
                providers=", ".join(PROVIDERS),
            )
        )
    scopes = value.get("scopes")
    if not isinstance(scopes, list) or not scopes or not all(isinstance(s, str) and s.strip() for s in scopes):
        raise ValueError(said("its oauth scopes must be a list of the scopes it needs"))
    return provider, [s.strip() for s in scopes]


def new_sign_in(server: McpServer, client_id: str, client_secret: str, redirect_uri: str) -> PluginSignIn:
    """Raises McpServerError for a plugin that doesn't sign in, or missing values."""
    if not server.oauth_provider:
        raise McpServerError(said("{name} doesn't sign in to anything.", name=server.name))
    if not client_id.strip() or not redirect_uri.strip():
        raise McpServerError(said("Enter your OAuth app's client ID."))
    return PluginSignIn(
        server.name,
        server.oauth_provider,
        tuple(server.oauth_scopes),
        client_id.strip(),
        client_secret.strip(),
        redirect_uri,
        secrets.token_urlsafe(64),
        expiry(),
    )


def authorization_url(sign_in: PluginSignIn, state: str) -> str:
    """The provider's sign-in page for it."""
    provider = PROVIDERS[sign_in.provider]
    query = {
        "client_id": sign_in.client_id,
        "response_type": "code",
        "redirect_uri": sign_in.redirect_uri,
        "scope": " ".join([*provider.identity, *sign_in.scopes]),
        "state": state,
        "code_challenge": challenge(sign_in.verifier),
        "code_challenge_method": "S256",
        **dict(provider.extra),
    }
    return f"{provider.auth_url}?{urlencode(query)}"


async def exchange(sign_in: PluginSignIn, code: str) -> Login:
    """The login for a code the provider sent back. Raises SignInError."""
    provider = PROVIDERS[sign_in.provider]
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": sign_in.redirect_uri,
        "code_verifier": sign_in.verifier,
    }
    answer = await _token_request(provider, sign_in.client_id, sign_in.client_secret, data)
    if not answer.get("refresh_token"):
        raise SignInError(said("{name} gave no refresh token; sign in again.", name=provider.name))
    return Login(
        provider.id,
        provider.token_url,
        sign_in.client_id,
        sign_in.client_secret,
        answer["refresh_token"],
        _account(str(answer.get("id_token", ""))),
        list(sign_in.scopes),
    )


async def login(store: BaseStore, box: SecretBox, name: str) -> Login | None:
    """The plugin's sign-in, or None when it isn't signed in or the key file can't read it."""
    try:
        saved = await keys.get(store, box, name)
    except SecretError:
        return None
    return Login.from_env(saved.env.get(ENV, ""))


async def signed_in_as(store: BaseStore, box: SecretBox, server: McpServer) -> str:
    """The account a plugin that signs in is signed in with; "" when it isn't, or doesn't sign in."""
    found = await login(store, box, server.name) if server.oauth_provider else None
    return (found.account or PROVIDERS[found.provider].name) if found else ""


async def _token_request(provider: Provider, client_id: str, client_secret: str, data: dict[str, str]) -> dict:
    form = {**data, "client_id": client_id, **({"client_secret": client_secret} if client_secret else {})}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
            response = await http.post(provider.token_url, data=form)
    except httpx.HTTPError as e:
        raise SignInError(said("Couldn't reach {name} to sign in: {error}", name=provider.name, error=e)) from e
    answer = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code != 200 or "access_token" not in answer:
        reason = answer.get("error_description") or answer.get("error") or f"HTTP {response.status_code}"
        raise SignInError(said("{name} refused the sign-in: {reason}", name=provider.name, reason=reason))
    return answer


def _account(id_token: str) -> str:
    """The address in the ID token the token endpoint answered with. It came straight from the provider over
    HTTPS, so its signature isn't checked; "" when there's none."""
    try:
        payload = id_token.split(".")[1]
        claims: Any = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return ""
    return str(claims.get("email", "")) if isinstance(claims, dict) else ""
