"""Passkeys (WebAuthn): a paired device adds one, and a browser signs in with it (Face ID, Touch ID,
a security key) instead of entering a pairing code. Each belongs to the device that added it, and
signing in with it gives the browser a new token of that device (core/devices.py), so revoking the
device revokes its passkeys too.

A passkey works only on the host it was made on (the relying party is the web app's host name),
and needs the user verified on the authenticator, not only present. The store keeps its public key,
which lets no one in by itself."""

import ipaddress
import logging
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from langgraph.store.base import BaseStore
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    base64url_to_bytes,
    bytes_to_base64url,
    options_to_json_dict,
    parse_authentication_credential_json,
    parse_registration_credential_json,
)
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from lo9i.core.devices import Device
from lo9i.core.i18n import said

logger = logging.getLogger(__name__)

_PASSKEYS = ("passkeys",)
# Long enough to find the phone and look at it.
_CEREMONY_SECONDS = 300
# Asking to sign in needs no device, so what waits is bounded: the oldest goes first.
_MAX_CEREMONIES = 64


class PasskeyError(Exception):
    pass


@dataclass(frozen=True)
class Site:
    """Where the browser is: the relying party (its host name) and the origin it signs for."""

    rp_id: str
    origin: str


@dataclass
class Passkey:
    id: str  # The credential's id, base64url.
    device_id: str
    host: str  # The host name it works on.
    # Kept by a password manager that syncs it to the user's other devices (iCloud Keychain, Google).
    synced: bool
    created_at: str
    last_used_at: str


@dataclass(frozen=True)
class Ceremony:
    """A registration or sign-in in progress: what the browser must sign, and where."""

    challenge: bytes
    site: Site
    # The device adding a passkey; None for a sign-in.
    device_id: str | None
    expires: float


class Ceremonies:
    """Ceremonies in progress, each taken once. Kept in memory: a restart only means asking again."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._open: OrderedDict[str, Ceremony] = OrderedDict()

    def open(self, site: Site, device_id: str | None) -> tuple[str, Ceremony]:
        while len(self._open) >= _MAX_CEREMONIES:
            self._open.popitem(last=False)
        ceremony = Ceremony(secrets.token_bytes(32), site, device_id, self._clock() + _CEREMONY_SECONDS)
        ceremony_id = secrets.token_urlsafe(16)
        self._open[ceremony_id] = ceremony
        return ceremony_id, ceremony

    def take(self, ceremony_id: str) -> Ceremony:
        """Raises PasskeyError when it's unknown, taken or expired."""
        ceremony = self._open.pop(ceremony_id, None)
        if ceremony is None or self._clock() > ceremony.expires:
            raise PasskeyError(said("That passkey request expired. Try again."))
        return ceremony


def site_for(scheme: str, host: str, port: int | None) -> Site:
    """The site a request came to. Raises PasskeyError where browsers allow no passkey: an IP address,
    or plain HTTP anywhere but localhost."""
    if _is_address(host) or (scheme != "https" and host != "localhost"):
        raise PasskeyError(said("Passkeys work only where the assistant is opened by its name over HTTPS."))
    default = 443 if scheme == "https" else 80
    return Site(host, f"{scheme}://{host}" + (f":{port}" if port and port != default else ""))


def registration_options(ceremony: Ceremony, device: Device, kept: list[Passkey], rp_name: str) -> dict[str, Any]:
    """What `navigator.credentials.create()` takes, as JSON. A passkey the authenticator already holds
    for this device isn't made again."""
    options = generate_registration_options(
        rp_id=ceremony.site.rp_id,
        rp_name=rp_name,
        user_id=device.id.encode(),
        user_name=device.name,
        challenge=ceremony.challenge,
        timeout=_CEREMONY_SECONDS * 1000,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.REQUIRED
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p.id)) for p in kept],
    )
    return options_to_json_dict(options)


def sign_in_options(ceremony: Ceremony) -> dict[str, Any]:
    """What `navigator.credentials.get()` takes, as JSON: any passkey for this host (the browser lists them)."""
    options = generate_authentication_options(
        rp_id=ceremony.site.rp_id,
        challenge=ceremony.challenge,
        timeout=_CEREMONY_SECONDS * 1000,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    return options_to_json_dict(options)


async def register(store: BaseStore, ceremony: Ceremony, credential: dict[str, Any], now: datetime) -> Passkey:
    """Keeps the passkey the browser made for the ceremony's device. Raises PasskeyError."""
    if ceremony.device_id is None:
        raise PasskeyError(said("Only a paired browser can add a passkey."))
    try:
        verified = verify_registration_response(
            credential=parse_registration_credential_json(credential),
            expected_challenge=ceremony.challenge,
            expected_rp_id=ceremony.site.rp_id,
            expected_origin=ceremony.site.origin,
            require_user_verification=True,
        )
    except WebAuthnException as e:
        logger.warning("A passkey couldn't be added: %s", e)
        raise PasskeyError(said("The passkey couldn't be checked. Try again.")) from e
    stamp = now.isoformat()
    passkey_id = bytes_to_base64url(verified.credential_id)
    passkey = Passkey(passkey_id, ceremony.device_id, ceremony.site.rp_id, verified.credential_backed_up, stamp, stamp)
    key = {"public_key": bytes_to_base64url(verified.credential_public_key), "sign_count": verified.sign_count}
    await store.aput(_PASSKEYS, passkey_id, {**asdict(passkey), **key})
    return passkey


async def authenticate(store: BaseStore, ceremony: Ceremony, credential: dict[str, Any], now: datetime) -> Passkey:
    """The passkey the browser signed in with, its use recorded. Raises PasskeyError."""
    try:
        parsed = parse_authentication_credential_json(credential)
    except WebAuthnException as e:
        raise PasskeyError(said("The passkey couldn't be checked. Try again.")) from e
    item = await store.aget(_PASSKEYS, bytes_to_base64url(parsed.raw_id))
    if item is None or item.value["host"] != ceremony.site.rp_id:
        raise PasskeyError(said("This passkey isn't known here any more. Pair this browser with a code."))
    try:
        verified = verify_authentication_response(
            credential=parsed,
            expected_challenge=ceremony.challenge,
            expected_rp_id=ceremony.site.rp_id,
            expected_origin=ceremony.site.origin,
            credential_public_key=base64url_to_bytes(item.value["public_key"]),
            credential_current_sign_count=item.value["sign_count"],
            require_user_verification=True,
        )
    except WebAuthnException as e:
        logger.warning("A sign-in with a passkey failed: %s", e)
        raise PasskeyError(said("The passkey couldn't be checked. Try again.")) from e
    value = {**item.value, "sign_count": verified.new_sign_count, "last_used_at": now.isoformat()}
    await store.aput(_PASSKEYS, item.key, value)
    return _passkey(value)


async def list_all(store: BaseStore) -> list[Passkey]:
    """Most recently used first."""
    passkeys = [_passkey(item.value) for item in await store.asearch(_PASSKEYS, limit=1000)]
    return sorted(passkeys, key=lambda p: p.last_used_at, reverse=True)


async def of_device(store: BaseStore, device_id: str) -> list[Passkey]:
    return [p for p in await list_all(store) if p.device_id == device_id]


async def remove(store: BaseStore, passkey_id: str) -> bool:
    """Whether a passkey with that id existed."""
    if await store.aget(_PASSKEYS, passkey_id) is None:
        return False
    await store.adelete(_PASSKEYS, passkey_id)
    return True


async def remove_of_device(store: BaseStore, device_id: str) -> None:
    for passkey in await of_device(store, device_id):
        await store.adelete(_PASSKEYS, passkey.id)


def _passkey(value: dict[str, Any]) -> Passkey:
    return Passkey(**{name: value[name] for name in Passkey.__dataclass_fields__})


def _is_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True
