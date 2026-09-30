from textual.widgets import Button, Input, Markdown

from assistant.gateways.cli.tui.screens import EmailScreen
from tests.cli.conftest import wait_for


async def test_connect_email_and_save_recipients(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/email", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, EmailScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#email-body", Markdown).source

        for field, value in {
            "email-host": "smtp.test",
            "email-port": "587",
            "email-user": "me",
            "email-password": "wrong",
            "email-sender": "me@test.com",
        }.items():
            screen.query_one(f"#{field}", Input).value = value
        screen.query_one("#connect", Button).press()
        await wait_for(pilot, lambda: "bad password" in body())
        screen.query_one("#email-password", Input).value = "right"
        screen.query_one("#connect", Button).press()
        await wait_for(pilot, lambda: "Email: me@test.com" in body())
        screen.query_one("#email-allowed", Input).value = "friend@test.com"
        screen.query_one("#recipients", Button).press()
        await wait_for(pilot, lambda: "friend@test.com" in body())
