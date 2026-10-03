from textual.widgets import Button, Markdown

from assistant_terminal.tui.screens import StartupScreen
from tests.terminal.conftest import wait_for


async def test_enable_cancel_and_disable(app, client):
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/startup", "enter")
        await wait_for(pilot, lambda: isinstance(app.screen, StartupScreen))
        screen = app.screen

        def body() -> str:
            return screen.query_one("#startup-body", Markdown).source

        await wait_for(pilot, lambda: "Start at boot: **off**" in body())
        client.system.cancel_password = True
        screen.query_one("#enable", Button).press()
        await wait_for(pilot, lambda: "Cancelled." in body())
        client.system.cancel_password = False
        screen.query_one("#enable", Button).press()
        await wait_for(pilot, lambda: "**on** (with Ollama)" in body() and "restarts under macOS" in body())
        assert not screen.query_one("#enable").display and screen.query_one("#disable").display
        screen.query_one("#disable", Button).press()
        await wait_for(pilot, lambda: "Start at boot: **off**" in body())


async def _open(pilot, app) -> StartupScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/startup", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, StartupScreen))
    return app.screen


async def test_on_linux_it_explains_the_service_and_lingering(app, client):
    from assistant.protocol import StartupStatus

    client.system.platform, client.system.lingering = "linux", False
    client.system.state = StartupStatus(False, False, False, "linux", False)
    async with app.run_test(size=(110, 40)) as pilot:
        screen = await _open(pilot, app)

        def body() -> str:
            return screen.query_one("#startup-body", Markdown).source

        await wait_for(pilot, lambda: "systemd user service" in body())
        assert "sudo loginctl enable-linger" in body() and "macOS" not in body()
        screen.query_one("#enable", Button).press()
        await wait_for(pilot, lambda: "restarts under systemd" in body())


async def test_unsupported_systems_offer_no_buttons(app, client):
    from assistant.protocol import StartupStatus

    client.system.state = StartupStatus(False, False, False, "unsupported")
    async with app.run_test(size=(110, 40)) as pilot:
        screen = await _open(pilot, app)
        await wait_for(pilot, lambda: "has neither" in screen.query_one("#startup-body", Markdown).source)
        assert not screen.query_one("#enable").display and not screen.query_one("#disable").display
