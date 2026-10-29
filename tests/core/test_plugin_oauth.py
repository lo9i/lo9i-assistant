"""Plugins that sign in with the user's own OAuth app (`oauth:` in their server.yaml, core/mcp/plugin_oauth.py): the
sign-in page, trading the code for a login, the login reaching the plugin's processes as one of its keys, and
signing out. The provider's token endpoint is a fake."""

import base64
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import pytest

from assistant.core.agent import McpServerError, ServerValues, SignInError
from assistant.core.events import ApprovalRequired, is_plugin_setup
from assistant.core.mcp import keys, plugin_oauth, servers
from assistant.core.mcp.install import FoundServer
from assistant.core.mcp.servers import McpServer
from assistant.core.repositories import cache
from assistant.core.repositories.known import EXTRAS
from tests.conftest import collect
from tests.core.test_repositories import HELLO, URL, _problems, _write, repo  # noqa: F401 (a fixture, used by `drive`)

REDIRECT = "https://board.ts.net:8443/app/oauth"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"

_DRIVE = f"""
description: Google Drive
command: "{{python}}"
args: ["{{dir}}/server.py"]
format: 5
fields:
  - {{key: DRIVE_FOLDER, label: Folder, optional: true}}
oauth:
  provider: google
  scopes: [{DRIVE_SCOPE}]
"""


def _id_token(claims: dict) -> str:
    """An ID token as the token endpoint sends it; only its claims are read."""
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"header.{payload}.signature"


@pytest.fixture
def google(monkeypatch) -> dict:
    """Google's token endpoint: what it was asked, and what it answers."""
    seen: dict = {"requests": [], "refuse": False, "answer": {}}

    async def token_request(provider, client_id, client_secret, data):
        seen["requests"].append({"url": provider.token_url, "client_id": client_id, "secret": client_secret, **data})
        if seen["refuse"]:
            raise SignInError("Google refused the sign-in: invalid_grant")
        default = {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "id_token": _id_token({"email": "me@x.com"}),
        }
        return seen["answer"] or default

    monkeypatch.setattr(plugin_oauth, "_token_request", token_request)
    return seen


@pytest.fixture
async def drive(service, repo):  # noqa: F811 (the fixture imported above)
    """The plugin, installed from the repository's productivity/documents folder."""
    _write(repo / "productivity" / "documents" / "drive", {"server.yaml": _DRIVE, "server.py": "print('drive')"})
    await service.install_from_repository(URL, [], [ServerValues("drive")])


async def _start(service, client_id: str = "client-1", secret: str = "secret-1") -> dict[str, list[str]]:
    return parse_qs(urlparse(await service.start_plugin_sign_in("drive", client_id, secret, REDIRECT)).query)


async def _signed_in(service, code: str = "code-1") -> None:
    signed_in = await service.finish_sign_in((await _start(service))["state"][0], code)
    assert (signed_in.kind, signed_in.id) == ("plugin", "drive")


async def _login(service) -> plugin_oauth.Login | None:
    """What the plugin's processes get, as they get it."""
    filled = await keys.fill(service.store, service.secrets, await servers.load(service.store, "drive"))
    return plugin_oauth.Login.from_env(filled.env[plugin_oauth.ENV])


async def _status(service):
    return next(s for s in await service.mcp_servers() if s.name == "drive")


async def test_a_plugin_that_signs_in_is_found_in_its_category_and_starts_signed_out(service, drive):
    found = next(s for s in (await service.browse_repository(URL)).servers if s.name == "drive")
    assert (found.oauth, found.category) == ("google", "productivity/documents")
    record = await servers.load(service.store, "drive")
    assert (record.oauth_provider, record.oauth_scopes) == ("google", [DRIVE_SCOPE])
    # Its sign-in is one of its keys, empty until the user signs in; the record keeps only its name.
    assert record.keys == ["DRIVE_FOLDER", plugin_oauth.ENV] and record.env[plugin_oauth.ENV] == ""
    assert await _login(service) is None
    status = await _status(service)
    assert (status.oauth, status.signed_in_as) == ("google", "")


async def test_the_sign_in_page_asks_for_the_plugins_scopes_with_pkce(service, drive):
    query = await _start(service)
    assert query["client_id"] == ["client-1"] and query["redirect_uri"] == [REDIRECT]
    assert query["scope"] == [f"openid email {DRIVE_SCOPE}"] and query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    with pytest.raises(McpServerError, match="client ID"):
        await _start(service, client_id=" ")


async def test_finishing_gives_the_plugin_its_login_and_keeps_it_encrypted(service, drive, google):
    await _signed_in(service)
    request = google["requests"][0]
    assert (request["code"], request["redirect_uri"], request["secret"]) == ("code-1", REDIRECT, "secret-1")
    assert request["url"] == "https://oauth2.googleapis.com/token" and len(request["code_verifier"]) > 40
    assert await _login(service) == plugin_oauth.Login(
        "google", "https://oauth2.googleapis.com/token", "client-1", "secret-1", "refresh-1", "me@x.com", [DRIVE_SCOPE]
    )
    assert (await _status(service)).signed_in_as == "me@x.com"
    # Only encrypted: not in its record, nor anywhere in the Store in the clear.
    assert (await servers.load(service.store, "drive")).env[plugin_oauth.ENV] == ""
    records = [item.value for ns in (("mcp_servers",), ("secrets",)) for item in await service.store.asearch(ns)]
    assert "refresh-1" not in str(records)
    with pytest.raises(SignInError, match="expired or was already used"):
        await service.finish_sign_in((await _start(service))["state"][0] + "x", "code-1")


async def test_signing_in_again_without_a_client_id_uses_the_app_it_signed_in_with(service, drive, google):
    await _signed_in(service)
    query = await _start(service, client_id="", secret="")
    assert query["client_id"] == ["client-1"]
    google["answer"] = {"access_token": "a", "refresh_token": "refresh-2"}
    await service.finish_sign_in(query["state"][0], "code-2")
    login = await _login(service)
    assert login is not None and (login.refresh_token, login.client_secret, login.account) == (
        "refresh-2",
        "secret-1",
        "",
    )
    # An ID token without an address: the provider's name stands for the account.
    assert (await _status(service)).signed_in_as == "Google"


async def test_a_refused_code_or_no_refresh_token_saves_nothing(service, drive, google):
    google["refuse"] = True
    with pytest.raises(SignInError, match="refused the sign-in"):
        await _signed_in(service)
    google.update(refuse=False, answer={"access_token": "a"})
    with pytest.raises(SignInError, match="gave no refresh token"):
        await _signed_in(service)
    assert await _login(service) is None


async def test_the_sign_in_stays_through_updates_and_removal_and_goes_when_signing_out(service, drive, google):
    await _signed_in(service)
    await service.update_mcp_server_from_repository("drive")
    assert (await _login(service)) is not None
    # Removed with its keys kept and installed again, it's still signed in.
    await service.remove_mcp_server("drive")
    await service.install_from_repository(URL, [], [ServerValues("drive", {"DRIVE_FOLDER": "Work"})])
    assert (await _login(service)) is not None
    status = await service.sign_out_plugin("drive")
    assert (status.signed_in_as, await _login(service)) == ("", None)
    # Its other keys stay.
    assert (await keys.get(service.store, service.secrets, "drive")).env == {"DRIVE_FOLDER": "Work"}


async def test_only_a_plugin_that_signs_in_can(service, drive, repo):  # noqa: F811
    await service.install_from_repository(URL, [], [HELLO])
    with pytest.raises(McpServerError, match="doesn't sign in"):
        await service.start_plugin_sign_in("hello", "client-1", "", REDIRECT)
    with pytest.raises(McpServerError, match="No MCP server named"):
        await service.start_plugin_sign_in("nope", "client-1", "", REDIRECT)


async def test_an_oauth_section_needs_format_5_a_known_provider_scopes_and_a_local_server(service, repo):  # noqa: F811
    general = repo / "other" / "general"
    _write(general / "old", {"server.yaml": _DRIVE.replace("format: 5", "format: 4")})
    _write(general / "dropbox", {"server.yaml": _DRIVE.replace("provider: google", "provider: dropbox")})
    _write(general / "bare", {"server.yaml": _DRIVE.replace(f"scopes: [{DRIVE_SCOPE}]", "scopes: []")})
    remote = "url: https://drive.example.com/mcp\nformat: 5\noauth: {provider: google, scopes: [x]}"
    _write(general / "remote", {"server.yaml": remote})
    problems = await _problems(service)
    assert "it signs in with oauth:, which needs format: 5" in problems
    assert "its oauth provider 'dropbox' isn't one of google" in problems
    assert "its oauth scopes must be a list of the scopes it needs" in problems
    assert "which is for plugins that run on this computer, not a url" in problems


def test_an_unreadable_id_token_or_login_is_nothing():
    assert plugin_oauth._account("not-a-token") == "" and plugin_oauth._account("a.!!!.b") == ""
    assert plugin_oauth.Login.from_env("") is None and plugin_oauth.Login.from_env("{oops") is None


async def test_open_plugin_setup_opens_the_sign_in_and_tells_how_it_went(service, script):
    found = FoundServer("drive", "Google Drive", "stdio", [], False, oauth="google")
    await cache.save(service.store, EXTRAS, cache.Listing("c1", [], [found]))
    env, signs_in = {plugin_oauth.ENV: ""}, [plugin_oauth.ENV]
    record = McpServer("drive", command="drive-mcp", env=env, source=EXTRAS, keys=signs_in, oauth_provider="google")
    await keys.save(service.store, service.secrets, record)
    script.call("open_plugin_setup", name="drive").reply("ok")
    session = await service.session("owner", "web")
    events = await collect(service.send(session, "connect my Google Drive"))
    setup = next(e for e in events if isinstance(e, ApprovalRequired))
    assert is_plugin_setup(setup.request) and setup.request["server"]["oauth"] == "google"
    login = plugin_oauth.Login("google", "t", "c", "s", "r", "me@x.com")
    await keys.save(service.store, service.secrets, replace(record, env={plugin_oauth.ENV: login.to_env()}))
    events = await collect(service.resume(session, {setup.interrupt_id: {"done": True}}))
    assert events[0].output == "The user closed drive's setup, signed in to Google as me@x.com."
