"""Devices that use the assistant over the network: pairing a new one with a one-time code (or, for the first one,
the setup code), recognizing it by its token, and revoking it with its passkeys."""

from datetime import UTC, datetime
from pathlib import Path

from lo9i.core import devices, passkeys, setup_code
from lo9i.core.agent.base import ServiceBase
from lo9i.core.config import settings
from lo9i.core.devices import Device, PairingCode
from lo9i.core.i18n import said

__all__ = ["Device", "DeviceError", "DevicesMixin", "PairingCode"]


class DeviceError(Exception):
    pass


class DevicesMixin(ServiceBase):
    async def prepare_setup_code(self) -> None:
        """At start: the setup code is written where no device was ever paired, and closed where one was."""
        await setup_code.prepare(self._storage.store, _setup_code_path(), datetime.now(UTC))

    async def setup_code_open(self) -> bool:
        """Whether no device was ever paired, so the first browser pairs with the setup code."""
        return await setup_code.available(self._storage.store, _setup_code_path())

    async def open_device_pairing(self) -> PairingCode:
        """A one-time code for pairing a new device. Only trusted clients may ask for one."""
        return await devices.open_pairing(self._storage.store, datetime.now(UTC))

    async def pair_device(self, code: str, name: str, ip: str) -> tuple[Device, str]:
        """The new device and its token, paired with a one-time code or the setup code. Raises DeviceError for a
        wrong or expired code."""
        store, now = self._storage.store, datetime.now(UTC)
        if not (
            await devices.take_pairing(store, code, now) or await setup_code.take(store, _setup_code_path(), code, now)
        ):
            raise DeviceError(said("That code is wrong or has expired. Create a new one and try again."))
        return await self._new_device(name, ip)

    async def device_for_token(self, token: str, ip: str) -> Device | None:
        return await devices.find(self._storage.store, token, ip, datetime.now(UTC))

    async def list_devices(self) -> list[Device]:
        return await devices.list_all(self._storage.store)

    async def revoke_device(self, device_id: str) -> None:
        """Raises DeviceError for an unknown device. Its passkeys go too, so they can't sign it in again."""
        if not await devices.revoke(self._storage.store, device_id):
            raise DeviceError(said("No device {device_id}.", device_id=device_id))
        await passkeys.remove_of_device(self._storage.store, device_id)

    async def _new_device(self, name: str, ip: str) -> tuple[Device, str]:
        """However it's paired, a device closes the setup code for good."""
        store, now = self._storage.store, datetime.now(UTC)
        added = await devices.add(store, name, ip, now)
        await setup_code.close(store, _setup_code_path(), now)
        return added


def _setup_code_path() -> Path:
    return Path(settings.setup_code_path).expanduser()
