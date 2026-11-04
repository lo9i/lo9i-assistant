"""Passkeys: a paired browser adds one, another browser signs in with it as that device without a
pairing code, and removing the passkey or revoking the device ends that. A software authenticator
plays the browser's part."""

import hashlib
import json
import secrets
import struct
from typing import Any

import cbor2
import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from lo9i.core.passkeys import Ceremonies, PasskeyError, Site, site_for
from lo9i.daemon.api import create_app
from lo9i.daemon.auth import trusted
from lo9i.daemon.runs import RunHub
from lo9i.protocol import CLIENT_HEADER

_UP, _UV, _AT = 0x01, 0x04, 0x40


class Authenticator:
    """A platform authenticator with one passkey, which counts its uses."""

    def __init__(self, origin: str = "https://localhost", verifies: bool = True) -> None:
        self.origin, self._verifies = origin, verifies
        self._key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(16)
        self._user: bytes = b""
        self._count = 0

    def create(self, options: dict[str, Any]) -> dict[str, Any]:
        self._user = base64url_to_bytes(options["user"]["id"])
        numbers = self._key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32), -3: numbers.y.to_bytes(32)})
        attested = bytes(16) + struct.pack(">H", len(self.credential_id)) + self.credential_id + cose
        data = self._data(options["rp"]["id"], _AT) + attested
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": data})
        response = {"clientDataJSON": self._client("webauthn.create", options), "attestationObject": _b64(attestation)}
        return self._credential(response)

    def get(self, options: dict[str, Any]) -> dict[str, Any]:
        self._count += 1
        data = self._data(options["rpId"], 0)
        client = self._client("webauthn.get", options)
        signed = data + hashlib.sha256(base64url_to_bytes(client)).digest()
        signature = self._key.sign(signed, ec.ECDSA(hashes.SHA256()))
        response = {
            "clientDataJSON": client,
            "authenticatorData": _b64(data),
            "signature": _b64(signature),
            "userHandle": _b64(self._user),
        }
        return self._credential(response)

    def _data(self, rp_id: str, flags: int) -> bytes:
        flags |= _UP | (_UV if self._verifies else 0)
        return hashlib.sha256(rp_id.encode()).digest() + bytes([flags]) + struct.pack(">I", self._count)

    def _client(self, kind: str, options: dict[str, Any]) -> str:
        return _b64(json.dumps({"type": kind, "challenge": options["challenge"], "origin": self.origin}).encode())

    def _credential(self, response: dict[str, str]) -> dict[str, Any]:
        cid = _b64(self.credential_id)
        return {"id": cid, "rawId": cid, "type": "public-key", "response": response, "clientExtensionResults": {}}


def _b64(data: bytes) -> str:
    return bytes_to_base64url(data)


@pytest.fixture
def app(service):
    return create_app(service, RunHub())


def _http(app, base_url: str = "https://localhost") -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=("203.0.113.7", 51000))
    return httpx.AsyncClient(transport=transport, base_url=base_url, headers={CLIENT_HEADER: "web"})


def _socket(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=trusted(app))
    return httpx.AsyncClient(transport=transport, base_url="http://lo9i", headers={CLIENT_HEADER: "cli"})


async def _paired(app, browser: httpx.AsyncClient, name: str = "Phone") -> dict[str, Any]:
    async with _socket(app) as cli:
        code = (await cli.post("/devices/pairing")).json()["code"]
    return (await browser.post("/auth/pair", json={"code": code, "name": name})).json()


async def _add(browser: httpx.AsyncClient, authenticator: Authenticator) -> httpx.Response:
    started = (await browser.post("/passkeys/options")).json()
    credential = authenticator.create(started["options"])
    return await browser.post("/passkeys", json={"ceremony": started["ceremony"], "credential": credential})


async def _sign_in(browser: httpx.AsyncClient, authenticator: Authenticator) -> httpx.Response:
    started = (await browser.post("/auth/passkey/options")).json()
    credential = authenticator.get(started["options"])
    return await browser.post("/auth/passkey", json={"ceremony": started["ceremony"], "credential": credential})


async def test_a_browser_signs_in_with_a_passkey_as_the_device_that_added_it(app):
    authenticator = Authenticator()
    async with _http(app) as phone:
        device = await _paired(app, phone)
        added = await _add(phone, authenticator)
        assert added.status_code == 200
        assert added.json()["device_id"] == device["id"] and added.json()["host"] == "localhost"
        async with _http(app) as laptop:
            assert (await laptop.get("/conversations")).status_code == 401
            signed_in = await _sign_in(laptop, authenticator)
            assert signed_in.status_code == 200 and signed_in.json()["id"] == device["id"]
            assert "lo9i_device=" in signed_in.headers["set-cookie"]
            assert (await laptop.get("/auth/me")).json()["device"]["id"] == device["id"]
        # The browser that added it stays signed in, and the device is listed once.
        assert (await phone.get("/conversations")).status_code == 200
        assert [d["id"] for d in (await phone.get("/devices")).json()] == [device["id"]]


async def test_the_options_ask_for_a_passkey_kept_on_the_authenticator_and_the_user_verified(app):
    async with _http(app) as phone:
        await _paired(app, phone, "Safari on iOS")
        options = (await phone.post("/passkeys/options")).json()["options"]
        assert options["rp"]["id"] == "localhost" and options["user"]["name"] == "Safari on iOS"
        assert options["authenticatorSelection"]["residentKey"] == "required"
        assert options["authenticatorSelection"]["userVerification"] == "required"
        await _add(phone, Authenticator())
        again = (await phone.post("/passkeys/options")).json()["options"]
        assert len(again["excludeCredentials"]) == 1
        assert (await phone.post("/auth/passkey/options")).json()["options"]["userVerification"] == "required"


async def test_revoking_the_device_revokes_its_passkeys(app):
    authenticator = Authenticator()
    async with _http(app) as phone, _http(app) as laptop:
        device = await _paired(app, phone)
        await _add(phone, authenticator)
        await _sign_in(laptop, authenticator)
        async with _socket(app) as cli:
            assert (await cli.delete(f"/devices/{device['id']}")).status_code == 200
            assert (await cli.get("/passkeys")).json() == []
        assert (await laptop.get("/conversations")).status_code == 401
        refused = await _sign_in(laptop, authenticator)
        assert refused.status_code == 400 and "isn't known here" in refused.json()["detail"]


async def test_a_removed_passkey_signs_in_no_more(app):
    authenticator = Authenticator()
    async with _http(app) as phone:
        await _paired(app, phone)
        passkey = (await _add(phone, authenticator)).json()
        assert [p["id"] for p in (await phone.get("/passkeys")).json()] == [passkey["id"]]
        assert (await phone.delete(f"/passkeys/{passkey['id']}")).status_code == 200
        assert (await phone.delete(f"/passkeys/{passkey['id']}")).status_code == 404
        async with _http(app) as laptop:
            assert (await _sign_in(laptop, authenticator)).status_code == 400


async def test_a_sign_in_is_refused_without_the_user_verified_or_from_another_origin(app):
    async with _http(app) as phone:
        await _paired(app, phone)
        unverified = Authenticator(verifies=False)
        assert (await _add(phone, unverified)).status_code == 400
        authenticator = Authenticator()
        await _add(phone, authenticator)
    authenticator.origin = "https://evil.example"
    async with _http(app) as other:
        assert (await _sign_in(other, authenticator)).status_code == 400
        assert (await other.get("/conversations")).status_code == 401


async def test_an_answer_counts_once(app):
    authenticator = Authenticator()
    async with _http(app) as phone:
        await _paired(app, phone)
        await _add(phone, authenticator)
    async with _http(app) as laptop:
        started = (await laptop.post("/auth/passkey/options")).json()
        body = {"ceremony": started["ceremony"], "credential": authenticator.get(started["options"])}
        assert (await laptop.post("/auth/passkey", json=body)).status_code == 200
        assert (await laptop.post("/auth/passkey", json=body)).status_code == 400


async def test_only_a_paired_browser_adds_one_and_not_at_an_ip_address(app):
    async with _socket(app) as cli:
        assert (await cli.post("/passkeys/options")).status_code == 403
        assert (await cli.get("/passkeys")).json() == []
    async with _http(app, "https://127.0.0.1") as browser:
        refused = await browser.post("/auth/passkey/options")
        assert refused.status_code == 400 and "by its name" in refused.json()["detail"]


def test_the_site_is_the_host_name_with_its_port_in_the_origin():
    assert site_for("https", "lo9i.example.com", None) == Site("lo9i.example.com", "https://lo9i.example.com")
    assert site_for("https", "lo9i.example.com", 8443).origin == "https://lo9i.example.com:8443"
    assert site_for("http", "localhost", 8765).origin == "http://localhost:8765"
    for scheme, host in (("http", "lo9i.example.com"), ("https", "192.168.0.33"), ("https", "::1")):
        with pytest.raises(PasskeyError):
            site_for(scheme, host, None)


def test_a_ceremony_expires():
    now = [0.0]
    ceremonies = Ceremonies(clock=lambda: now[0])
    ceremony_id, _ = ceremonies.open(Site("localhost", "https://localhost"), None)
    now[0] = 301
    with pytest.raises(PasskeyError):
        ceremonies.take(ceremony_id)
