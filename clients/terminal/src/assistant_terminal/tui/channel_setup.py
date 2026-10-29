"""A chat channel's setup, shown in its plugin's details in /plugins: whether it's connected, and what
it shows for setting it up. Each channel sends its own items (lines, a code to read out, a value to
copy, a QR code to scan, buttons), so this draws them without knowing any channel."""

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Static, TextArea

from assistant.client import clipboard
from assistant.client.daemon_client import ChannelsApi
from assistant.core.agent import ChannelNotConnectedError, ChannelStatus, SetupItem
from assistant_terminal.channels_text import heading, line, qr_lines, title
from assistant_terminal.i18n import t
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable


class _ActionButton(Button):
    """A channel's setup button: pressing it sends its action to the channel."""

    def __init__(self, channel: ChannelStatus, item: SetupItem) -> None:
        super().__init__(item.label, disabled=not channel.connected, classes="channel-action")
        # Not `action`: a Button runs its `action` instead of reporting a press.
        self.channel, self.channel_action = channel.name, item.value


class _CopyButton(Button):
    def __init__(self, item: SetupItem) -> None:
        super().__init__(
            t("Copy {label}", label=item.label) if item.label else t("Copy"), classes="channel-copy-button"
        )
        self.copy_name, self.copy_value = item.label, item.value


class ChannelSetup(Vertical):
    def __init__(self, channels: ChannelsApi, channel: ChannelStatus) -> None:
        super().__init__(classes="channel-setup")
        self._channels, self._channel = channels, channel

    def compose(self) -> ComposeResult:
        yield from _channel_widgets(self._channel)

    @on(Button.Pressed, ".channel-action")
    @reports_daemon_unavailable
    async def _press(self, event: Button.Pressed) -> None:
        button = event.button
        if not isinstance(button, _ActionButton):
            return
        event.stop()
        try:
            await self._channels.press(button.channel, button.channel_action)
        except ChannelNotConnectedError:
            self.notify(
                t("{channel} isn't connected, so it can't do that now.", channel=title(button.channel)),
                severity="warning",
            )

    @on(Button.Pressed, ".channel-copy-button")
    async def _copy(self, event: Button.Pressed) -> None:
        """With this machine's clipboard command, and through the terminal (OSC 52), which reaches
        the clipboard of the computer in front of you over SSH, in terminals that support it."""
        button = event.button
        if not isinstance(button, _CopyButton):
            return
        event.stop()
        self.app.copy_to_clipboard(button.copy_value)
        copied = await clipboard.copy(button.copy_value)
        if not copied:
            self.notify(t("Sent it to your terminal's clipboard."))
        else:
            self.notify(t("Copied {name}.", name=button.copy_name) if button.copy_name else t("Copied it."))


def _channel_widgets(channel: ChannelStatus) -> list[Widget]:
    widgets: list[Widget] = [Static(heading(channel), markup=False, classes="channel-heading")]
    for item in channel.items:
        widgets.extend(_item_widgets(item))
    actions = [_ActionButton(channel, item) for item in channel.items if item.kind == "action"]
    if actions:
        widgets.append(Horizontal(*actions, classes="channel-actions"))
    return widgets


def _item_widgets(item: SetupItem) -> list[Widget]:
    """Actions aren't here: they go together in a row after the channel's items."""
    if item.kind == "code":
        label = f"{item.label}: " if item.label else ""
        return [Static(Text.assemble(label, (item.value, "bold")), classes="channel-code")]
    if item.kind == "copy":
        return [
            Static(item.label, markup=False),
            TextArea(item.value, read_only=True, classes="channel-copy"),
            Horizontal(_CopyButton(item), classes="channel-actions"),
        ]
    if item.kind == "qr":
        return _qr_widgets(item)
    if item.kind == "action":
        return []
    return [Static(line(item), markup=False)]


def _qr_widgets(item: SetupItem) -> list[Widget]:
    """Black on white whatever the theme: phones read a QR code best that way."""
    code = Text("\n".join(qr_lines(item.value)), style="#000000 on #ffffff", no_wrap=True)
    return [*([Static(item.label, markup=False)] if item.label else []), Static(code, classes="channel-qr")]
