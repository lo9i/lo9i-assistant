import builtins

from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import Device, DeviceError, PairingCode, Passkey, PasskeyError

_NOT_FOUND = {404: DeviceError}
_NO_PASSKEY = {404: PasskeyError}


class DevicesApi:
    """Devices (browsers on other hosts) allowed to use the daemon over the network: pair a new one
    with a one-time code, list them, revoke them, and the passkeys they sign in with."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def list(self) -> list[Device]:
        """Most recently used first."""
        return [Device(**d) for d in await self._transport.request("GET", "/devices")]

    async def open_pairing(self) -> PairingCode:
        """A one-time code to enter on the new device, replacing any earlier one."""
        return PairingCode(**await self._transport.request("POST", "/devices/pairing"))

    async def revoke(self, device_id: str) -> None:
        """Raises DeviceError for an unknown device."""
        await self._transport.request("DELETE", f"/devices/{device_id}", errors=_NOT_FOUND)

    async def passkeys(self) -> builtins.list[Passkey]:
        """Every device's, most recently used first. Only a browser adds one."""
        return [Passkey(**p) for p in await self._transport.request("GET", "/passkeys")]

    async def remove_passkey(self, passkey_id: str) -> None:
        """Raises PasskeyError for an unknown passkey."""
        await self._transport.request("DELETE", f"/passkeys/{passkey_id}", errors=_NO_PASSKEY)
