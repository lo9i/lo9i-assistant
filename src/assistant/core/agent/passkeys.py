"""Passkeys: a paired device adds one, a browser signs in as that device with it instead of a
pairing code, and the user lists and removes them (core/passkeys.py)."""

from datetime import UTC, datetime
from typing import Any

from assistant.core import devices, identity, passkeys
from assistant.core.agent.base import ServiceBase
from assistant.core.devices import Device
from assistant.core.i18n import said
from assistant.core.passkeys import Passkey, PasskeyError, Site

__all__ = ["Passkey", "PasskeyError", "PasskeysMixin", "Site"]

# The name a password manager shows for the passkey's site while the assistant has none of its own.
_UNNAMED = "lo9i"


class PasskeysMixin(ServiceBase):
    async def passkey_options(self, site: Site, device: Device) -> tuple[str, dict[str, Any]]:
        """A ceremony for `device` to add a passkey, and what the browser makes it from."""
        ceremony_id, ceremony = self._passkey_ceremonies.open(site, device.id)
        kept = await passkeys.of_device(self._storage.store, device.id)
        name = await identity.load_name(self._storage.store) or _UNNAMED
        return ceremony_id, passkeys.registration_options(ceremony, device, kept, name)

    async def add_passkey(self, ceremony_id: str, credential: dict[str, Any]) -> Passkey:
        """Raises PasskeyError when the ceremony expired or the browser's answer doesn't check out."""
        ceremony = self._passkey_ceremonies.take(ceremony_id)
        return await passkeys.register(self._storage.store, ceremony, credential, datetime.now(UTC))

    def passkey_sign_in_options(self, site: Site) -> tuple[str, dict[str, Any]]:
        ceremony_id, ceremony = self._passkey_ceremonies.open(site, None)
        return ceremony_id, passkeys.sign_in_options(ceremony)

    async def sign_in_with_passkey(self, ceremony_id: str, credential: dict[str, Any], ip: str) -> tuple[Device, str]:
        """The device the passkey belongs to and a new token of it for this browser. Raises PasskeyError."""
        store, now = self._storage.store, datetime.now(UTC)
        passkey = await passkeys.authenticate(store, self._passkey_ceremonies.take(ceremony_id), credential, now)
        signed_in = await devices.add_token(store, passkey.device_id, ip, now)
        if signed_in is None:
            # Its device was revoked some other way than revoke_device: it goes with it.
            await passkeys.remove(store, passkey.id)
            raise PasskeyError(said("This passkey isn't known here any more. Pair this browser with a code."))
        return signed_in

    async def list_passkeys(self) -> list[Passkey]:
        return await passkeys.list_all(self._storage.store)

    async def remove_passkey(self, passkey_id: str) -> None:
        """Raises PasskeyError for an unknown passkey."""
        if not await passkeys.remove(self._storage.store, passkey_id):
            raise PasskeyError(said("No passkey {passkey_id}.", passkey_id=passkey_id))
