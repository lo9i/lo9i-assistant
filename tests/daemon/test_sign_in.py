"""Signing a browser in over the network without a client on the computer itself: the setup code while no device was
ever paired, and links emailed to the owner, which never say whether an address is the owner's."""

from pathlib import Path

import httpx
import pytest

import lo9i.core.integrations.email.smtp as sending
from lo9i.core.config import settings
from lo9i.daemon.api import create_app
from lo9i.daemon.auth import COOKIE, trusted
from lo9i.daemon.runs import RunHub
from lo9i.protocol import CLIENT_HEADER

_SITE = "https://lo9i.local:8443"


@pytest.fixture
def app(service, monkeypatch):
    monkeypatch.setattr(settings, "https_host", "lo9i.example.com")
    monkeypatch.setattr(settings, "https_other_hosts", ["lo9i.local", "lo9i.example.ts.net"])
    return create_app(service, RunHub())


@pytest.fixture
def sent(monkeypatch) -> list[tuple[list[str], str]]:
    mail: list[tuple[list[str], str]] = []

    async def verify(config):
        pass

    async def send(config, to, subject, body, attachments=()):
        mail.append((to, body))

    monkeypatch.setattr(sending, "verify", verify)
    monkeypatch.setattr(sending, "send", send)
    return mail


def _browser(app, site: str = _SITE, ip: str = "203.0.113.7") -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(ip, 51000))
    return httpx.AsyncClient(transport=transport, base_url=site, headers={CLIENT_HEADER: "web"})


def _socket(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=trusted(app))
    return httpx.AsyncClient(transport=transport, base_url="http://lo9i", headers={CLIENT_HEADER: "cli"})


async def test_the_first_browser_pairs_with_the_setup_code(app, service):
    Path(settings.setup_code_path).write_text("K7QM-2XPD\n")
    async with _browser(app) as browser:
        assert (await browser.get("/auth/sign-in")).json() == {"setup": True, "email_link": False}
        response = await browser.post("/auth/pair", json={"code": "k7qm2xpd", "name": "iPhone"})
        assert response.status_code == 200 and f"{COOKIE}=" in response.headers["set-cookie"]
        assert (await browser.get("/auth/sign-in")).json()["setup"] is False
    async with _browser(app, ip="203.0.113.8") as other:
        assert (await other.post("/auth/pair", json={"code": "K7QM-2XPD", "name": "Thief"})).status_code == 400


async def test_a_link_signs_a_browser_in_on_the_site_it_was_asked_from(app, service, sent):
    async with _socket(app) as cli:
        await service.add_email_account("", "smtp.test", 587, "me", "pw", "me@test.com")
        async with _browser(app) as browser:
            assert (await browser.get("/auth/sign-in")).json() == {"setup": False, "email_link": True}
            for address in ("me@test.com", "nobody@test.com"):
                answer = await browser.post("/auth/link", json={"email": address})
                assert answer.status_code == 200 and answer.json() == {"ok": True}
            [(to, body)] = sent
            assert to == ["me@test.com"] and f"{_SITE}/app/sign-in#" in body
            token = body.split("#", 1)[1].split()[0]
            async with _browser(app, "https://lo9i.example.ts.net:8443") as elsewhere:
                assert (
                    await elsewhere.post("/auth/link/finish", json={"token": token, "name": "x"})
                ).status_code == 400
            finished = await browser.post("/auth/link/finish", json={"token": token, "name": "iPhone"})
            assert finished.status_code == 200 and f"{COOKIE}=" in finished.headers["set-cookie"]
            assert (await browser.get("/auth/me")).json()["device"]["name"] == "iPhone"
            again = await browser.post("/auth/link/finish", json={"token": token, "name": "iPhone"})
            assert again.status_code == 400
        assert [d["name"] for d in (await cli.get("/devices")).json()] == ["iPhone"]


async def test_asking_for_links_is_limited_per_address(app, sent):
    async with _browser(app) as browser:
        for _ in range(5):
            assert (await browser.post("/auth/link", json={"email": "me@test.com"})).status_code == 200
        assert (await browser.post("/auth/link", json={"email": "me@test.com"})).status_code == 429


async def test_only_the_daemons_own_names_are_answered(app):
    async with _browser(app, "https://lo9i.example.ts.net:8443") as known:
        assert (await known.get("/auth/sign-in")).status_code == 200
    async with _browser(app, "https://evil.example:8443") as unknown:
        assert (await unknown.get("/auth/sign-in")).status_code == 403
