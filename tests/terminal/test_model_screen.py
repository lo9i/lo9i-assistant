from textual.widgets import Button, Input, Markdown, Select

from assistant_terminal.tui.screens import ModelScreen
from tests.terminal.conftest import wait_for


async def _open(pilot, app) -> ModelScreen:
    await pilot.click("#prompt")
    await pilot.press(*"/model", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, ModelScreen))
    return app.screen


async def test_switch_to_copilot_after_a_failed_test_then_back_to_env(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app)

        def body() -> str:
            return screen.query_one("#model-body", Markdown).source

        await wait_for(pilot, lambda: "Anthropic (from .env)" in body())
        assert not screen.query_one("#reset").display
        screen.query_one("#model-provider", Select).value = "copilot"
        main = screen.query_one("#model-main", Input)
        await wait_for(pilot, lambda: main.value == "claude-opus-5.5")
        assert not screen.query_one("#model-url").display
        screen.query_one("#model-key", Input).value = "bad"
        screen.query_one("#save", Button).press()
        await wait_for(pilot, lambda: "401 invalid key" in body())
        screen.query_one("#model-key", Input).value = "gh-token"
        screen.query_one("#save", Button).press()
        await wait_for(pilot, lambda: "GitHub Copilot (set here)" in body())
        assert client.model.saved == ("copilot", "gh-token", "", "claude-opus-5.5", "claude-sonnet-5.5")
        assert screen.query_one("#model-key", Input).value == ""  # never kept on screen
        screen.query_one("#reset", Button).press()
        await wait_for(pilot, lambda: "Anthropic (from .env)" in body())


async def test_openai_compatible_asks_for_the_server(app, client):
    async with app.run_test(size=(110, 44)) as pilot:
        screen = await _open(pilot, app)
        screen.query_one("#model-provider", Select).value = "openai"
        await wait_for(pilot, lambda: screen.query_one("#model-url").display)
        assert screen.query_one("#model-main", Input).value == ""
