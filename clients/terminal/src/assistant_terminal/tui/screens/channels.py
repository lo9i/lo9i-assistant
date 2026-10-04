"""Chat channels (Telegram, Slack), installed as plugins: whether each is connected, and what it shows
for setting it up. Each channel sends its own items (lines, a code to read out, a value to copy,
buttons), so this screen draws them without knowing any channel. Refreshes when the daemon reports a
change, so a new pairing code or a finished pairing shows up by itself."""

from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Markdown, Static, TextArea

from assistant.client import clipboard
from assistant.client.daemon_client import ChannelsApi
from assistant.core.agent import ChannelNotConnectedError, ChannelStatus, SetupItem
from assistant_terminal.channels_text import NONE_INSTALLED, heading, line, title
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_INTRO = """## Channels

Chat with the assistant from other apps. Channels are plugins: install, update or remove them in
/plugins."""


class _ActionButton(Button):
    """A channel's setup button: pressing it sends its action to the channel."""

    def __init__(self, channel: ChannelStatus, item: SetupItem) -> None:
        super().__init__(item.label, disabled=not channel.connected, classes="channel-action")
        # Not `action`: a Button runs its `action` instead of reporting a press.
        self.channel, self.channel_action = channel.name, item.value


class _CopyButton(Button):
    def __init__(self, item: SetupItem) -> None:
        super().__init__(f"Copy {item.label}" if item.label else "Copy", classes="channel-copy-button")
        self.copy_name, self.copy_value = item.label or "it", item.value


class ChannelsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, channels: ChannelsApi) -> None:
        super().__init__()
        self._channels = channels

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="channels"):
            yield Markdown(_INTRO)
            yield Vertical(id="channels-list")
            with Horizontal(id="channels-buttons"):
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when the daemon reports a change: a channel connected, or changed what it shows."""
        channels = await self._channels.list()
        box = self.query_one("#channels-list", Vertical)
        await box.remove_children()
        if not channels:
            await box.mount(Static(NONE_INSTALLED, markup=False, classes="channel-empty"))
            return
        await box.mount_all([w for channel in channels for w in _channel_widgets(channel)])

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, ".channel-action")
    @reports_daemon_unavailable
    async def _press(self, event: Button.Pressed) -> None:
        button = event.button
        if not isinstance(button, _ActionButton):
            return
        try:
            await self._channels.press(button.channel, button.channel_action)
        except ChannelNotConnectedError:
            self.notify(f"{title(button.channel)} isn't connected, so it can't do that now.", severity="warning")

    @on(Button.Pressed, ".channel-copy-button")
    async def _copy(self, event: Button.Pressed) -> None:
        """With this machine's clipboard command, and through the terminal (OSC 52), which reaches
        the clipboard of the computer in front of you over SSH, in terminals that support it."""
        button = event.button
        if not isinstance(button, _CopyButton):
            return
        self.app.copy_to_clipboard(button.copy_value)
        copied = await clipboard.copy(button.copy_value)
        self.notify(f"Copied {button.copy_name}." if copied else "Sent it to your terminal's clipboard.")


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
    if item.kind == "action":
        return []
    return [Static(line(item), markup=False)]
