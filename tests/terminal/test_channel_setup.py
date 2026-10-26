"""A chat channel's setup, in its plugin's details in /plugins."""

import segno
from rich.text import Text
from textual.widgets import Button, Markdown, Static, TextArea

from assistant.core.agent import ChannelStatus, FoundServer, SetupItem
from assistant_terminal.channels_text import describe, qr_lines
from assistant_terminal.tui.screens import PluginsScreen
from tests.terminal.conftest import wait_for

_PAIRING = [
    SetupItem("text", "", "Bot: @lo9i_bot"),
    SetupItem("code", "Pairing code", "lo9i-4821"),
    SetupItem("action", "New pairing code", "new_pairing_code"),
]


def _channel(name: str, installed: bool = True) -> FoundServer:
    return FoundServer(
        name, "Chat", "none", [], True, channel=True, installed=installed, category="communications/chat"
    )


async def _open(pilot, app, client, *channels: FoundServer) -> PluginsScreen:
    """Communications comes first, so its first channel is shown."""
    client.repositories.more = list(channels)
    await pilot.click("#prompt")
    await pilot.press(*"/plugins", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, PluginsScreen))
    return app.screen


def _text(screen) -> str:
    return "\n".join(str(s.render()) for s in screen.query("#plugin-setup Static"))


async def test_draws_what_a_channel_sends_and_presses_its_buttons(app, client):
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app, client, _channel("telegram"))
        await wait_for(pilot, lambda: "Telegram · not connected" in _text(screen))
        client.channels.items["telegram"] = ChannelStatus("telegram", True, True, _PAIRING)
        await client.bus.put(("channels", {}))  # the plugin connected and sent its pairing code
        await wait_for(pilot, lambda: "Pairing code: lo9i-4821" in _text(screen))
        assert "Telegram · connected ✓" in _text(screen) and "Bot: @lo9i_bot" in _text(screen)
        screen.query_one(".channel-action", Button).press()
        await wait_for(pilot, lambda: client.channels.pressed == [("telegram", "new_pairing_code")])


async def test_buttons_wait_for_the_channel_to_connect(app, client):
    client.channels.items["telegram"] = ChannelStatus("telegram", True, False, _PAIRING)
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app, client, _channel("telegram"))
        await wait_for(pilot, lambda: bool(screen.query(".channel-action")))
        assert screen.query_one(".channel-action", Button).disabled


async def test_a_value_to_copy_shows_in_a_box_with_a_copy_button(app, client):
    manifest = '{"display_information": {"name": "lo9i"}}'
    copy = SetupItem("copy", "App manifest", manifest)
    client.channels.items = {"slack": ChannelStatus("slack", False, False, [copy])}
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app, client, _channel("slack"))
        await wait_for(pilot, lambda: bool(screen.query(".channel-copy")))
        assert screen.query_one(".channel-copy", TextArea).text == manifest
        assert "Slack · off" in _text(screen)
        assert str(screen.query_one(".channel-copy-button", Button).label) == "Copy App manifest"


_LINK = "https://wa.me/settings/linked_devices#2@AbCdEf,GhIjKl,MnOpQr"


def test_a_qr_code_is_drawn_two_modules_to_a_character():
    """Each character's top and bottom halves are the modules above and below, quiet border included."""
    halves = {"█": (True, True), "▀": (True, False), "▄": (False, True), " ": (False, False)}
    rows: list[list[bool]] = []
    for text in qr_lines(_LINK):
        pairs = [halves[character] for character in text]
        rows += [[top for top, _ in pairs], [bottom for _, bottom in pairs]]
    matrix = [[bool(module) for module in row] for row in segno.make_qr(_LINK).matrix_iter(border=2)]
    # An odd number of rows gets a light one below.
    assert rows[: len(matrix)] == matrix and not any(any(row) for row in rows[len(matrix) :])


async def test_a_qr_code_to_scan_shows_black_on_white(app, client):
    qr = SetupItem("qr", "Scan with WhatsApp", _LINK)
    client.channels.items = {"whatsapp": ChannelStatus("whatsapp", True, True, [qr])}
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app, client, _channel("whatsapp"))
        await wait_for(pilot, lambda: bool(screen.query(".channel-qr")))
        code = screen.query_one(".channel-qr", Static).content
        assert isinstance(code, Text) and code.plain.splitlines() == qr_lines(_LINK)
        assert str(code.style) == "#000000 on #ffffff"
        assert "Scan with WhatsApp" in _text(screen)
    assert "QR code: Scan with WhatsApp (scan it in the full-screen app" in describe(
        ChannelStatus("whatsapp", True, True, [qr])
    )


async def test_a_channel_not_installed_has_no_setup(app, client):
    async with app.run_test(size=(120, 44)) as pilot:
        screen = await _open(pilot, app, client, _channel("telegram", installed=False))
        await wait_for(pilot, lambda: "## telegram" in screen.query_one("#plugin-body", Markdown).source)
        assert not screen.query("#plugin-setup Static")


def test_the_plain_repl_shows_items_as_text():
    text = describe(ChannelStatus("telegram", True, True, _PAIRING))
    assert "**Telegram · connected ✓**" in text
    assert "Pairing code: **`lo9i-4821`**" in text and "Bot: @lo9i_bot" in text
    assert "Button: New pairing code" in text
