from textual.widgets import Button, Static, TextArea

from assistant.core.agent import ChannelStatus, SetupItem
from assistant_terminal.channels_text import describe
from assistant_terminal.tui.screens import ChannelsScreen
from tests.terminal.conftest import wait_for

_PAIRING = [
    SetupItem("text", "", "Bot: @lo9i_bot"),
    SetupItem("code", "Pairing code", "lo9i-4821"),
    SetupItem("action", "New pairing code", "new_pairing_code"),
]


async def _open(pilot, app) -> ChannelsScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/channels", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, ChannelsScreen))
    return app.screen


def _text(screen) -> str:
    return "\n".join(str(s.render()) for s in screen.query("#channels-list Static"))


async def test_draws_what_a_channel_sends_and_presses_its_buttons(app, client):
    async with app.run_test(size=(110, 40)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: "Telegram · not connected" in _text(screen))
        client.channels.items["telegram"] = ChannelStatus("telegram", True, True, _PAIRING)
        await client.bus.put(("channels", {}))  # the plugin connected and sent its pairing code
        await wait_for(pilot, lambda: "Pairing code: lo9i-4821" in _text(screen))
        assert "Telegram · connected ✓" in _text(screen) and "Bot: @lo9i_bot" in _text(screen)
        screen.query_one(".channel-action", Button).press()
        await wait_for(pilot, lambda: client.channels.pressed == [("telegram", "new_pairing_code")])
        await pilot.press("escape")
        await wait_for(pilot, lambda: not isinstance(app.screen, ChannelsScreen))


async def test_buttons_wait_for_the_channel_to_connect(app, client):
    client.channels.items["telegram"] = ChannelStatus("telegram", True, False, _PAIRING)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: bool(screen.query(".channel-action")))
        assert screen.query_one(".channel-action", Button).disabled


async def test_a_value_to_copy_shows_in_a_box_with_a_copy_button(app, client):
    manifest = '{"display_information": {"name": "lo9i"}}'
    copy = SetupItem("copy", "App manifest", manifest)
    client.channels.items = {"slack": ChannelStatus("slack", False, False, [copy])}
    async with app.run_test(size=(110, 40)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: bool(screen.query(".channel-copy")))
        assert screen.query_one(".channel-copy", TextArea).text == manifest
        assert "Slack · off" in _text(screen)
        assert str(screen.query_one(".channel-copy-button", Button).label) == "Copy App manifest"


async def test_with_no_channel_it_says_where_to_install_one(app, client):
    client.channels.items = {}
    async with app.run_test(size=(110, 40)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: bool(screen.query(".channel-empty")))
        assert "/plugins" in str(screen.query_one(".channel-empty", Static).render())


def test_the_plain_repl_shows_items_as_text():
    text = describe(ChannelStatus("telegram", True, True, _PAIRING))
    assert "**Telegram · connected ✓**" in text
    assert "Pairing code: **`lo9i-4821`**" in text and "Bot: @lo9i_bot" in text
    assert "Button: New pairing code" in text
