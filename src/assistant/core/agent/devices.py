"""Devices that use the assistant over the network: pairing a new one with a one-time code,
recognizing it by its token, and revoking it."""

from datetime import UTC, datetime

from assistant.core import devices
from assistant.core.agent.base import ServiceBase
from assistant.core.devices import Device, PairingCode
from assistant.core.i18n import said

__all__ = ["Device", "DeviceError", "DevicesMixin", "PairingCode"]


class DeviceError(Exception):
    pass


class DevicesMixin(ServiceBase):
    async def open_device_pairing(self) -> PairingCode:
        """A one-time code for pairing a new device. Only trusted clients may ask for one."""
        return await devices.open_pairing(self._storage.store, datetime.now(UTC))

    async def pair_device(self, code: str, name: str, ip: str) -> tuple[Device, str]:
        """The new device and its token. Raises DeviceError for a wrong or expired code."""
        store, now = self._storage.store, datetime.now(UTC)
        if not await devices.take_pairing(store, code, now):
            raise DeviceError(said("That code is wrong or has expired. Create a new one and try again."))
        return await devices.add(store, name, ip, now)

    async def device_for_token(self, token: str, ip: str) -> Device | None:
        return await devices.find(self._storage.store, token, ip, datetime.now(UTC))

    async def list_devices(self) -> list[Device]:
        return await devices.list_all(self._storage.store)

    async def revoke_device(self, device_id: str) -> None:
        """Raises DeviceError for an unknown device."""
        if not await devices.revoke(self._storage.store, device_id):
            raise DeviceError(said("No device {device_id}.", device_id=device_id))
