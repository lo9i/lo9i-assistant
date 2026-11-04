"""Signing in to Google and Microsoft mail with OAuth: the sign-in page, trading the code for
tokens, logging in with XOAUTH2, and refreshing tokens. The provider and the mail servers are fakes."""

import json
import time
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import pytest

from lo9i.core.agent import EmailAccount, EmailError, SignInError
from lo9i.core.integrations.email import accounts, imap, oauth, smtp
from lo9i.core.integrations.email.accounts import EmailConfig

REDIRECT = "https://board.ts.net:8443/app/oauth"


@pytest.fixture
def provider(monkeypatch) -> dict:
    """The provider's token endpoint: what it was asked, and whether it refuses."""
    seen: dict = {"requests": [], "refuse": False, "n": 0}

    async def token_request(provider_id, client_id, client_secret, data, personal=False):
        seen["requests"].append({"provider": provider_id, "client_id": client_id, "secret": client_secret, **data})
        if seen["refuse"]:
            raise EmailError("Google refused the sign-in: invalid_grant")
        seen["n"] += 1
        return {"access_token": f"access-{seen['n']}", "refresh_token": "refresh-1", "expires_in": 3600}

    monkeypatch.setattr(oauth, "_token_request", token_request)
    return seen


@pytest.fixture
def servers(monkeypatch) -> list[EmailConfig]:
    """The SMTP and IMAP log-in checks, recording the settings they were given."""
    checked: list[EmailConfig] = []

    async def verify(config):
        checked.append(config)

    monkeypatch.setattr(smtp, "verify", verify)
    monkeypatch.setattr(imap, "verify", verify)
    return checked


async def _finish(service, state: str, code: str) -> EmailAccount:
    signed_in = await service.finish_sign_in(state, code)
    assert signed_in.kind == "email"
    return next(a for a in await service.email_accounts() if a.id == signed_in.id)


async def _start(service, provider_id="google", **extra) -> dict[str, list[str]]:
    url = await service.start_email_sign_in(provider_id, "client-1", "secret-1", REDIRECT, "me@gmail.com", **extra)
    return parse_qs(urlparse(url).query)


async def test_the_sign_in_page_asks_for_mail_with_pkce(service):
    query = await _start(service)
    assert query["client_id"] == ["client-1"] and query["redirect_uri"] == [REDIRECT]
    assert query["scope"] == ["https://mail.google.com/"] and query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"] and query["login_hint"] == ["me@gmail.com"]
    microsoft = await _start(service, "microsoft")
    assert "https://outlook.office.com/SMTP.Send" in microsoft["scope"][0] and "offline_access" in microsoft["scope"][0]
    with pytest.raises(EmailError, match="isn't supported"):
        await _start(service, "yahoo")


async def test_finishing_trades_the_code_checks_the_servers_and_saves_the_account(service, provider, servers):
    query = await _start(service, label="Personal")
    account = await _finish(service, query["state"][0], "code-1")
    assert (account.auth, account.oauth_provider, account.host, account.imap_host) == (
        "oauth",
        "google",
        "smtp.gmail.com",
        "imap.gmail.com",
    )
    assert (account.label, account.sender, account.username) == ("Personal", "me@gmail.com", "me@gmail.com")
    request = provider["requests"][0]
    assert (request["code"], request["redirect_uri"], request["secret"]) == ("code-1", REDIRECT, "secret-1")
    assert len(request["code_verifier"]) > 40
    assert [(c.auth, c.password) for c in servers] == [("oauth", "access-1"), ("oauth", "access-1")]
    with pytest.raises(SignInError, match="expired or was already used"):
        await service.finish_sign_in(query["state"][0], "code-1")


async def test_a_refused_code_saves_nothing(service, provider, servers):
    provider["refuse"] = True
    query = await _start(service)
    with pytest.raises(EmailError, match="refused the sign-in"):
        await service.finish_sign_in(query["state"][0], "bad")
    assert await service.email_accounts() == []


async def test_an_expired_access_token_is_refreshed_when_the_account_is_loaded(service, provider, servers):
    await service.finish_sign_in((await _start(service))["state"][0], "code-1")
    [account] = await service.email_accounts()
    secret = json.loads(await _secret(service, account.id))
    secret["expires_at"] = time.time() - 10
    await _save_secret(service, account.id, json.dumps(secret))
    config = await accounts.load(service.store, service.secrets)
    assert (
        config.password == "access-2" and json.loads(await _secret(service, account.id))["access_token"] == "access-2"
    )


async def test_a_refused_refresh_asks_to_sign_in_again(service, provider, servers):
    await service.finish_sign_in((await _start(service))["state"][0], "code-1")
    [account] = await service.email_accounts()
    secret = json.loads(await _secret(service, account.id))
    secret["expires_at"] = 0
    await _save_secret(service, account.id, json.dumps(secret))
    provider["refuse"] = True
    with pytest.raises(EmailError, match="needs to sign in again"):
        await accounts.load(service.store, service.secrets)
    [account] = await service.email_accounts()
    assert account.status == "needs_sign_in"
    # Signing in again reuses the OAuth app it signed in with.
    page = await service.start_email_sign_in("google", "", "", REDIRECT, "me@gmail.com", account_id=account.id)
    query = parse_qs(urlparse(page).query)
    assert query["client_id"] == ["client-1"]
    provider["refuse"] = False
    again = await _finish(service, query["state"][0], "code-2")
    assert (again.id, again.status) == (account.id, "ok")


async def test_smtp_and_imap_log_in_with_the_token(monkeypatch):
    calls: list[tuple] = []

    class _Smtp:
        def __init__(self, **kwargs):
            pass

        async def connect(self):
            pass

        async def auth_xoauth2(self, user, token):
            calls.append(("smtp", user, token))

        async def quit(self):
            pass

    monkeypatch.setattr(smtp.aiosmtplib, "SMTP", _Smtp)
    config = EmailConfig("smtp.gmail.com", 587, "me@gmail.com", "token-1", "me@gmail.com", auth="oauth")
    await smtp.verify(config)

    class _Imap:
        async def xoauth2(self, user, token):
            calls.append(("imap", user, token))
            return "ok"

    assert await imap._log_in(cast(Any, _Imap()), config) == "ok"
    assert calls == [("smtp", "me@gmail.com", "token-1"), ("imap", "me@gmail.com", "token-1")]


async def _secret(service, account_id: str) -> str:
    from lo9i.core import accounts as core_accounts

    account = await core_accounts.get(service.store, "email", account_id)
    assert account is not None
    return await core_accounts.secret(service.store, service.secrets, account)


async def _save_secret(service, account_id: str, text: str) -> None:
    from lo9i.core import accounts as core_accounts

    account = await core_accounts.get(service.store, "email", account_id)
    assert account is not None
    await core_accounts.set_secret(service.store, service.secrets, account, text)


async def test_the_token_request_sends_the_app_and_reads_the_providers_refusal(monkeypatch):
    import httpx

    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if b"refresh_token=gone" in request.content:
            return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Token has been revoked."})
        return httpx.Response(200, json={"access_token": "a", "expires_in": 60})

    real = httpx.AsyncClient
    monkeypatch.setattr(oauth.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(answer), **kw))
    refreshed = await oauth.refresh(oauth.Tokens("microsoft", "client-1", "", "refresh-1"))
    assert refreshed.access_token == "a" and refreshed.refresh_token == "refresh-1"
    form = parse_qs(seen[0].content.decode())
    assert form == {"grant_type": ["refresh_token"], "refresh_token": ["refresh-1"], "client_id": ["client-1"]}
    assert str(seen[0].url) == oauth.PROVIDERS["microsoft"].token_url
    with pytest.raises(EmailError, match="Token has been revoked"):
        await oauth.refresh(oauth.Tokens("google", "c", "s", "gone"))


_BUILT_IN = oauth.PROVIDERS["microsoft"].built_in_client_id
_LOCAL = "http://localhost:8765/app/oauth"


def _token_endpoint(monkeypatch, seen: list) -> None:
    """Microsoft's token endpoint, recording each request."""
    import httpx

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"access_token": "a", "refresh_token": "r2", "expires_in": 60})

    real = httpx.AsyncClient
    monkeypatch.setattr(oauth.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(answer), **kw))


async def test_microsoft_signs_in_with_lo9is_public_app_sending_no_secret(monkeypatch):
    seen: list = []
    _token_endpoint(monkeypatch, seen)
    # A secret typed without a client ID of one's own isn't sent: Microsoft refuses one from a public client.
    sign_in = oauth.new_sign_in("microsoft", "", "stray", _LOCAL, "me@hotmail.com", "", "")
    query = parse_qs(urlparse(oauth.authorization_url(sign_in, "s1")).query)
    assert query["client_id"] == [_BUILT_IN] and query["code_challenge_method"] == ["S256"]
    tokens = await oauth.exchange(sign_in, "code-1")
    form = parse_qs(seen[0].content.decode())
    assert form["client_id"] == [_BUILT_IN] and "client_secret" not in form and form["code_verifier"]
    assert str(seen[0].url).startswith("https://login.microsoftonline.com/consumers/")
    assert (tokens.client_id, tokens.client_secret, tokens.refresh_token) == (_BUILT_IN, "", "r2")
    await oauth.refresh(tokens)
    assert "client_secret" not in parse_qs(seen[1].content.decode())


async def test_an_account_signed_in_with_its_own_app_refreshes_with_that_apps_secret(monkeypatch):
    seen: list = []
    _token_endpoint(monkeypatch, seen)
    saved = oauth.Tokens("microsoft", "own-app", "own-secret", "r1", personal=True).to_secret()
    refreshed = await oauth.refresh(oauth.Tokens.from_secret(saved))
    form = parse_qs(seen[0].content.decode())
    assert form["client_id"] == ["own-app"] and form["client_secret"] == ["own-secret"]
    assert str(seen[0].url).startswith("https://login.microsoftonline.com/consumers/")
    assert (refreshed.client_id, refreshed.client_secret, refreshed.refresh_token) == ("own-app", "own-secret", "r2")


def test_lo9is_app_sends_the_browser_back_only_to_this_computer():
    for redirect in (_LOCAL, "http://127.0.0.1:8765/app/oauth"):
        assert oauth.new_sign_in("microsoft", "", "", redirect, "me@outlook.com", "", "").client_id == _BUILT_IN
    with pytest.raises(EmailError, match="on the computer it runs on"):
        oauth.new_sign_in("microsoft", "", "", REDIRECT, "me@outlook.com", "", "")
    # One's own app goes wherever it was registered to, with its secret.
    own = oauth.new_sign_in("microsoft", "own-app", "own-secret", REDIRECT, "me@contoso.com", "", "")
    assert (own.client_id, own.client_secret) == ("own-app", "own-secret")
    # Google has no app of lo9i's.
    with pytest.raises(EmailError, match="client ID"):
        oauth.new_sign_in("google", "", "", _LOCAL, "me@gmail.com", "", "")


async def test_signing_in_again_keeps_the_app_the_account_signed_in_with(service, provider, servers):
    first = await service.start_email_sign_in("microsoft", "own-app", "own-secret", REDIRECT, "me@hotmail.com")
    account = await _finish(service, parse_qs(urlparse(first).query)["state"][0], "code-1")
    again = await service.start_email_sign_in("microsoft", "", "", REDIRECT, "me@hotmail.com", account_id=account.id)
    assert parse_qs(urlparse(again).query)["client_id"] == ["own-app"]
    await _finish(service, parse_qs(urlparse(again).query)["state"][0], "code-2")
    assert provider["requests"][-1]["secret"] == "own-secret"
