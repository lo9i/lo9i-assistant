"""Devices allowed to use the assistant over the network: pair a new browser with a one-time code,
see where each one was last used and its passkeys, remove those, and revoke it. Refreshes when a
device or passkey changes."""

from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client import clipboard
from assistant.client.daemon_client import DevicesApi
from assistant.core.agent import Device, DeviceError, PairingCode, Passkey, PasskeyError
from assistant_terminal.devices_text import describe, pairing
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen

_EMPTY = translatable("No devices paired yet. Pair a browser to use the assistant from another computer.")


class DevicesScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", translatable("Close"))]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"devices"})

    def __init__(self, devices: DevicesApi) -> None:
        super().__init__()
        self._devices = devices
        self._shown: dict[str, Device] = {}
        self._passkeys: list[Passkey] = []
        self._selected: str | None = None
        # The code shown, while it is.
        self._code: PairingCode | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="devices"):
            yield Static(t("Devices"), id="devices-title")
            with Horizontal(id="devices-main"):
                yield OptionList(id="devices-list")
                yield Static(classes="divider")
                with VerticalScroll(id="devices-detail"):
                    yield Markdown(id="device-body")
            with Horizontal(id="devices-buttons"):
                yield Button(t("Pair a browser"), variant="success", id="pair")
                yield Button(t("Copy code"), id="copy")
                yield Button(t("Remove passkeys"), variant="warning", id="remove-passkeys")
                yield Button(t("Revoke"), variant="error", id="revoke")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a device is paired, used or revoked, or a passkey added or removed."""
        devices = await self._devices.list()
        self._passkeys = await self._devices.passkeys()
        self._shown = {d.id: d for d in devices}
        options = self.query_one("#devices-list", OptionList)
        options.clear_options()
        options.add_options([Option(d.name, id=d.id) for d in devices])
        self.query_one("#revoke").display = bool(devices)
        if self._selected not in self._shown:
            self._selected = devices[0].id if devices else None
        if self._selected is None:
            await self._body(t(_EMPTY))
            return
        options.highlighted = list(self._shown).index(self._selected)
        await self._show(self._selected)

    @reports_daemon_unavailable
    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id in self._shown:
            self._selected = event.option.id
            await self._show(event.option.id)

    async def _show(self, device_id: str) -> None:
        passkeys = self._passkeys_of(device_id)
        await self._body(describe(self._shown[device_id], passkeys))
        self.query_one("#remove-passkeys").display = bool(passkeys)

    def _passkeys_of(self, device_id: str) -> list[Passkey]:
        return [p for p in self._passkeys if p.device_id == device_id]

    @on(Button.Pressed, "#pair")
    @reports_daemon_unavailable
    async def _pair(self) -> None:
        code = await self._devices.open_pairing()
        await self._body(pairing(code))
        self._code = code
        self.query_one("#copy").display = True

    @on(Button.Pressed, "#copy")
    async def _copy(self) -> None:
        """With this machine's clipboard command, and through the terminal (OSC 52), which reaches
        the clipboard of the computer in front of you over SSH, in terminals that support it."""
        if self._code is None:
            return
        self.app.copy_to_clipboard(self._code.code)
        copied = await clipboard.copy(self._code.code)
        code = self._code.code
        self.notify(
            t("Copied {name}.", name=code) if copied else t("Sent {code} to your terminal's clipboard.", code=code)
        )

    @on(Button.Pressed, "#remove-passkeys")
    def _remove_passkeys(self) -> None:
        device = self._shown.get(self._selected or "")
        if device is not None:
            self._confirm_remove_passkeys(device)

    @on(Button.Pressed, "#revoke")
    def _revoke(self) -> None:
        device = self._shown.get(self._selected or "")
        if device is not None:
            self._confirm_revoke(device)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @work
    @reports_daemon_unavailable
    async def _confirm_remove_passkeys(self, device: Device) -> None:
        question = t(
            "Remove {name}'s passkeys? They won't sign in any more; delete them from the password manager too.",
            name=device.name,
        )
        if not await self.app.push_screen_wait(ConfirmScreen(question, t("Remove"))):
            return
        for passkey in self._passkeys_of(device.id):
            try:
                await self._devices.remove_passkey(passkey.id)
            except PasskeyError as e:
                self.notify(str(e), severity="error")
        await self.reload()

    @work
    @reports_daemon_unavailable
    async def _confirm_revoke(self, device: Device) -> None:
        question = t(
            "Revoke {name}? It will need a new code to use the assistant again. Its passkeys are removed too.",
            name=device.name,
        )
        if not await self.app.push_screen_wait(ConfirmScreen(question, t("Revoke"))):
            return
        try:
            await self._devices.revoke(device.id)
        except DeviceError as e:
            self.notify(str(e), severity="error")
        await self.reload()

    async def _body(self, markdown: str) -> None:
        """Showing anything else hides the code and its copy button."""
        self._code = None
        self.query_one("#copy").display = False
        self.query_one("#remove-passkeys").display = False
        await self.query_one("#device-body", Markdown).update(markdown)
