from textual.widgets import Button, Input, Markdown, Select

from assistant.gateways.cli.tui.screens import EmailScreen
from tests.cli.conftest import wait_for


async def _open(pilot, app) -> EmailScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/email", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, EmailScreen))
    return app.screen


def _body(screen) -> str:
    return screen.query_one("#email-body", Markdown).source


async def test_a_provider_needs_only_the_address_and_password(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app)
        screen.query_one("#email-provider", Select).value = "gmail"
        await wait_for(pilot, lambda: screen.query_one("#email-address").display)
        assert not screen.query_one("#email-host").display
        assert "myaccount.google.com/apppasswords" in screen.query_one("#email-help", Markdown).source
        screen.query_one("#email-address", Input).value = "me@gmail.com"
        screen.query_one("#email-password", Input).value = "right"
        screen.query_one("#connect", Button).press()
        await wait_for(pilot, lambda: "Email: me@gmail.com" in _body(screen))
        assert client.email.connected_with == ("smtp.gmail.com", 587, "me@gmail.com", "right", "me@gmail.com")


async def test_microsoft_explains_it_cant_connect_yet(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app)
        screen.query_one("#email-provider", Select).value = "microsoft"
        await wait_for(pilot, lambda: "OAuth" in screen.query_one("#email-help", Markdown).source)
        assert not screen.query_one("#connect").display and not screen.query_one("#email-password").display


async def test_other_asks_for_the_server_and_saves_recipients(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app)
        screen.query_one("#email-provider", Select).value = "other"
        await wait_for(pilot, lambda: screen.query_one("#email-host").display)
        for field, value in {
            "email-host": "smtp.test",
            "email-port": "587",
            "email-user": "me",
            "email-password": "wrong",
            "email-sender": "me@test.com",
        }.items():
            screen.query_one(f"#{field}", Input).value = value
        screen.query_one("#connect", Button).press()
        await wait_for(pilot, lambda: "bad password" in _body(screen))
        screen.query_one("#email-password", Input).value = "right"
        screen.query_one("#connect", Button).press()
        await wait_for(pilot, lambda: "Email: me@test.com" in _body(screen))
        screen.query_one("#email-allowed", Input).value = "friend@test.com"
        screen.query_one("#recipients", Button).press()
        await wait_for(pilot, lambda: "friend@test.com" in _body(screen))
